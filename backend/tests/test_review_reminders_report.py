"""Findings from the independent review: reminder clock semantics, report reconciliation, solver limit."""
from __future__ import annotations

import time
from datetime import timedelta

from sqlalchemy import select, update

from app.models import DebtState, Outbox, now_utc
from app.money import OPTIMAL_LIMIT, minimal_transfers
from app.reminders import run_reminders


def _mails(db, g):
    db.expire_all()
    return db.scalars(select(Outbox).where(Outbox.group_id == g["id"], Outbox.kind == "reminder")).all()


def test_weekly_cap_survives_a_debt_that_was_paid_and_returned(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b], remind=1)
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    t0 = now_utc()
    run_reminders(db, t0 + timedelta(days=2))
    assert len(_mails(db, g)) == 1
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 500}, headers=b["h"]).json()
    client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))  # b owes again
    run_reminders(db, t0 + timedelta(days=3))
    assert len(_mails(db, g)) == 1  # still inside the week since the last reminder
    run_reminders(db, t0 + timedelta(days=10))
    assert len(_mails(db, g)) == 2


def test_closed_time_does_not_count_towards_the_reminder_term(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b], remind=3)
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    db.execute(update(DebtState).where(DebtState.group_id == g["id"]).values(since=now_utc() - timedelta(days=30)))
    db.commit()
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    client.post(f"/api/groups/{g['id']}/reopen", headers=a["h"])
    t0 = now_utc()
    run_reminders(db, t0 + timedelta(days=1))
    assert len(_mails(db, g)) == 0  # the clock restarted on reopen
    run_reminders(db, t0 + timedelta(days=4))
    assert len(_mails(db, g)) == 1


def test_report_numbers_reconcile_after_a_settlement(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 200}, headers=b["h"]).json()
    client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"])
    report = client.get(f"/api/groups/{g['id']}/report", headers=a["h"]).json()
    for m in report["members"]:
        assert m["paid_minor"] - m["share_minor"] + m["settled_out_minor"] - m["settled_in_minor"] == m["balance_minor"]
    assert sum(m["balance_minor"] for m in report["members"]) == 0


def test_exact_solver_limit_is_fast_and_settles_everyone():
    n = OPTIMAL_LIMIT
    vals = [(-1) ** i * (i + 1) * 100 for i in range(n)]
    vals[-1] -= sum(vals)
    balances = {i + 1: v for i, v in enumerate(vals)}
    start = time.perf_counter()
    transfers = minimal_transfers(balances)
    assert time.perf_counter() - start < 2.0
    out = dict(balances)
    for t in transfers:
        out[t.from_user] += t.amount
        out[t.to_user] -= t.amount
    assert all(v == 0 for v in out.values())


def test_editing_an_expense_down_warns_when_a_confirmed_payment_is_now_too_big(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    e = api.expense(g, a, a, 1000, api.equal(ids)).json()          # b owes 500
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 400}, headers=b["h"]).json()
    client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"])  # b now owes 100
    body = {"payer_id": a["id"], "amount_minor": 400, "title": "x", "category": "food", "spent_on": "2026-10-01", "split": api.equal(ids)}
    r = client.put(f"/api/groups/{g['id']}/expenses/{e['id']}", json=body, headers=a["h"])
    assert r.status_code == 200
    assert r.json()["warnings"] == [{"user_id": b["id"], "name": b["name"], "amount_minor": 200}]  # b paid 400, owed 200
    assert api.balances(g, a) == {a["id"]: -200, b["id"]: 200}
    feed = client.get(f"/api/groups/{g['id']}/activity", headers=a["h"]).json()
    assert feed[0]["kind"] == "settlement_overpaid"
    ok = client.put(f"/api/groups/{g['id']}/expenses/{e['id']}", json={**body, "amount_minor": 1000}, headers=a["h"])
    assert ok.json()["warnings"] == []  # back to a normal debt: nothing to warn about
    gone = client.delete(f"/api/groups/{g['id']}/expenses/{e['id']}", headers=a["h"]).json()
    assert gone["warnings"] == [{"user_id": b["id"], "name": b["name"], "amount_minor": 400}]
