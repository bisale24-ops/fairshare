from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import select

from app.models import Notification, Outbox, now_utc
from app.reminders import run_reminders


def test_register_login_me_and_duplicate(client, api):
    u = api.user()
    assert client.get("/api/auth/me", headers=u["h"]).json()["email"] == u["email"]
    assert client.post("/api/auth/register", json={"email": u["email"], "name": "x", "password": "secret1"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "bad-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "secret1"}).status_code == 200
    assert client.get("/api/groups").status_code == 401


def test_group_invite_by_link_and_by_email(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a)
    assert client.get(f"/api/groups/{g['id']}", headers=b["h"]).status_code == 404  # not a member yet
    info = client.get(f"/api/join/{g['invite_token']}").json()
    assert info["name"] == "Trip" and info["currency"] == "USD"
    assert client.post(f"/api/join/{g['invite_token']}", headers=b["h"]).status_code == 200
    assert client.post(f"/api/join/{g['invite_token']}", headers=b["h"]).status_code == 200  # idempotent
    assert len(api.group_view(g, b)["members"]) == 2
    r = client.post(f"/api/groups/{g['id']}/invites", json={"email": "friend@example.com"}, headers=a["h"])
    assert r.status_code == 201
    mail = db.scalar(select(Outbox).where(Outbox.to_email == "friend@example.com"))
    assert mail and g["invite_token"] in mail.body


def test_equal_split_keeps_every_cent_and_balances_sum_to_zero(api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])
    r = api.expense(g, a, a, 100, api.equal([a["id"], b["id"], c["id"]]))
    assert r.status_code == 201
    shares = {s["user_id"]: s["amount_minor"] for s in r.json()["shares"]}
    assert sum(shares.values()) == 100
    lowest = min(shares)
    assert shares[lowest] == 34  # leftover cent goes to the lowest user id, always
    bal = api.balances(g, a)
    assert sum(bal.values()) == 0
    assert bal[a["id"]] == 100 - shares[a["id"]]


def test_shares_and_exact_splits_and_validation(api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    r = api.expense(g, a, a, 1000, {"type": "shares", "weights": {str(a["id"]): 1, str(b["id"]): 3}})
    assert r.status_code == 201
    assert {s["user_id"]: s["amount_minor"] for s in r.json()["shares"]} == {a["id"]: 250, b["id"]: 750}
    ok = api.expense(g, a, b, 500, {"type": "exact", "amounts": {str(a["id"]): 200, str(b["id"]): 300}})
    assert ok.status_code == 201
    bad = api.expense(g, a, b, 500, {"type": "exact", "amounts": {str(a["id"]): 200, str(b["id"]): 299}})
    assert bad.status_code == 422
    stranger = api.user()
    assert api.expense(g, a, a, 500, api.equal([a["id"], stranger["id"]])).status_code == 422
    assert api.expense(g, stranger, a, 500, api.equal([a["id"]])).status_code == 404


def test_group_view_proposes_minimal_transfers(api):
    a, b, c, d = (api.user() for _ in range(4))
    g = api.group(a, [b, c, d])
    api.expense(g, a, a, 4000, api.equal([a["id"], b["id"], c["id"], d["id"]]))
    view = api.group_view(g, a)
    assert len(view["transfers"]) == 3  # b, c, d each pay a once, not everyone-to-everyone
    assert all(t["to_user"] == a["id"] for t in view["transfers"])


def test_edit_and_delete_recompute_everything_including_settlements(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    e = api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]])).json()
    assert api.balances(g, a) == {a["id"]: 500, b["id"]: -500}
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 200}, headers=b["h"]).json()
    assert api.balances(g, a) == {a["id"]: 500, b["id"]: -500}  # pending: not counted yet
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 200
    assert api.balances(g, a) == {a["id"]: 300, b["id"]: -300}
    body = {"payer_id": a["id"], "amount_minor": 2000, "title": "dinner", "category": "food", "spent_on": "2026-10-02", "split": api.equal([a["id"], b["id"]])}
    assert client.put(f"/api/groups/{g['id']}/expenses/{e['id']}", json=body, headers=a["h"]).status_code == 200
    assert api.balances(g, a) == {a["id"]: 800, b["id"]: -800}  # 1000 owed, 200 already settled
    assert client.delete(f"/api/groups/{g['id']}/expenses/{e['id']}", headers=a["h"]).status_code == 200
    bal = api.balances(g, a)
    assert sum(bal.values()) == 0 and bal == {a["id"]: -200, b["id"]: 200}  # settlement stays; recomputed honestly


def test_settlement_rules(client, api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])
    api.expense(g, a, a, 3000, api.equal([a["id"], b["id"], c["id"]]))
    url = f"/api/groups/{g['id']}/settlements"
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 1001}, headers=b["h"]).status_code == 409  # more than owed
    assert client.post(url, json={"to_user": b["id"], "amount_minor": 100}, headers=a["h"]).status_code == 409  # a owes nothing
    assert client.post(url, json={"to_user": b["id"], "amount_minor": 100}, headers=c["h"]).status_code == 409  # b is owed nothing
    s = client.post(url, json={"to_user": a["id"], "amount_minor": 400}, headers=b["h"]).json()
    assert s["status"] == "pending"
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=b["h"]).status_code == 403  # only the receiver
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 200
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 409  # already resolved
    assert api.balances(g, a)[b["id"]] == -600  # partial payment of 400 out of 1000
    r = client.post(url, json={"to_user": a["id"], "amount_minor": 100}, headers=c["h"]).json()
    assert client.post(f"/api/settlements/{r['id']}/reject", headers=a["h"]).status_code == 200
    assert api.balances(g, a)[c["id"]] == -1000


def test_notifications_on_expense_with_me_and_on_edit(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    e = api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]])).json()
    texts = [n["text"] for n in client.get("/api/notifications", headers=b["h"]).json()]
    assert any("added" in t for t in texts)
    assert not client.get("/api/notifications", headers=a["h"]).json()  # nothing for the author
    body = {"payer_id": a["id"], "amount_minor": 1200, "title": "dinner", "category": "food", "spent_on": "2026-10-01", "split": api.equal([a["id"], b["id"]])}
    client.put(f"/api/groups/{g['id']}/expenses/{e['id']}", json=body, headers=a["h"])
    assert any("edited" in n["text"] for n in client.get("/api/notifications", headers=b["h"]).json())
    feed = client.get(f"/api/groups/{g['id']}/activity", headers=b["h"]).json()
    assert [f["kind"] for f in feed][:2] == ["expense_edited", "expense_added"]


def test_two_concurrent_expenses_both_counted_and_balances_sum_to_zero(api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])
    ids = [a["id"], b["id"], c["id"]]
    users = [a, b, c]

    def add(i: int):
        who = users[i % 3]
        return api.expense(g, who, who, 1000 + i, api.equal(ids)).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = list(pool.map(add, range(30)))
    assert codes == [201] * 30
    expenses = api.c.get(f"/api/groups/{g['id']}/expenses", headers=a["h"]).json()
    assert len(expenses) == 30
    assert sum(e["amount_minor"] for e in expenses) == sum(1000 + i for i in range(30))
    bal = api.balances(g, a)
    assert sum(bal.values()) == 0


def test_closed_group_blocks_expenses_sends_summary_and_reopens(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    r = client.post(f"/api/groups/{g['id']}/close", headers=b["h"])
    assert r.status_code == 200 and r.json()["total_spent_minor"] == 1000
    mails = db.scalars(select(Outbox).where(Outbox.group_id == g["id"], Outbox.kind == "close_summary")).all()
    assert {m.to_email for m in mails} == {a["email"], b["email"]}
    assert "pays" in mails[0].body
    assert api.expense(g, a, a, 500, api.equal([a["id"]])).status_code == 409
    assert client.post(f"/api/groups/{g['id']}/close", headers=a["h"]).status_code == 409
    assert client.post(f"/api/groups/{g['id']}/reopen", headers=a["h"]).status_code == 200
    assert api.expense(g, a, a, 500, api.equal([a["id"]])).status_code == 201


def test_reminders_after_term_once_a_week_never_when_paid(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b], remind=3)
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    t0 = now_utc()

    def mails():
        db.expire_all()
        return db.scalars(select(Outbox).where(Outbox.group_id == g["id"], Outbox.kind == "reminder")).all()

    run_reminders(db, t0 + timedelta(days=2))
    assert len(mails()) == 0  # term (3 days) not reached
    run_reminders(db, t0 + timedelta(days=4))
    assert len(mails()) == 1 and mails()[0].to_email == b["email"]
    assert "5.00 USD to" in mails()[0].body
    run_reminders(db, t0 + timedelta(days=6))
    assert len(mails()) == 1  # not twice within a week
    run_reminders(db, t0 + timedelta(days=12))
    assert len(mails()) == 2
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 500}, headers=b["h"]).json()
    client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"])
    run_reminders(db, t0 + timedelta(days=30))
    assert len(mails()) == 2  # debt paid: no more reminders


def test_balances_across_all_groups_are_netted_per_person_and_currency(client, api):
    a, b = api.user(), api.user()
    g1, g2, g3 = api.group(a, [b]), api.group(a, [b]), api.group(a, [b], currency="EUR")
    api.expense(g1, a, a, 1000, api.equal([a["id"], b["id"]]))  # b owes a 5.00
    api.expense(g2, b, b, 400, api.equal([a["id"], b["id"]]))  # a owes b 2.00
    api.expense(g3, a, a, 600, api.equal([a["id"], b["id"]]))  # b owes a 3.00 EUR
    data = {x["currency"]: x for x in client.get("/api/me/balances", headers=a["h"]).json()}
    assert data["USD"]["net_minor"] == 300
    assert data["USD"]["people"] == [{"user_id": b["id"], "name": b["name"], "amount_minor": 300}]
    assert data["EUR"]["net_minor"] == 300 and len(data["USD"]["groups"]) == 2


def test_receipt_upload_validation(client, api):
    a = api.user()
    g = api.group(a)
    e = api.expense(g, a, a, 1000, api.equal([a["id"]])).json()
    url = f"/api/groups/{g['id']}/expenses/{e['id']}/receipt"
    assert client.post(url, files={"file": ("x.exe", b"MZ", "application/x-msdownload")}, headers=a["h"]).status_code == 415
    assert client.post(url, files={"file": ("big.png", b"0" * (5 * 1024 * 1024 + 10), "image/png")}, headers=a["h"]).status_code == 413
    assert client.post(url, files={"file": ("r.png", b"\x89PNG data", "image/png")}, headers=a["h"]).status_code == 200
    got = client.get(url, headers=a["h"])
    assert got.status_code == 200 and got.content == b"\x89PNG data"
    assert client.get(url, headers=api.user()["h"]).status_code == 404
