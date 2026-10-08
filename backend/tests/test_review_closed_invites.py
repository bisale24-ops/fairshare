"""Findings from the independent review: closed group is frozen, join is serialised, invites are real."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Outbox


def _setup(api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    return a, b, g


def test_closed_group_rejects_new_and_pending_settlement_actions(client, api):
    a, b, g = _setup(api)
    assert client.post(f"/api/groups/{g['id']}/close", headers=a["h"]).status_code == 200
    r = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 100}, headers=b["h"])
    assert r.status_code == 409 and "closed" in r.json()["detail"]
    assert api.balances(g, a) == {a["id"]: 500, b["id"]: -500}  # the e-mailed summary is final


def test_cannot_close_while_a_payment_is_pending(client, api):
    a, b, g = _setup(api)
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 100}, headers=b["h"]).json()
    r = client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    assert r.status_code == 409 and "pending" in r.json()["detail"]
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 200
    assert client.post(f"/api/groups/{g['id']}/close", headers=a["h"]).status_code == 200
    # a payment confirmed before closing stays confirmed; nothing can change afterwards
    assert client.post(f"/api/settlements/{s['id']}/reject", headers=a["h"]).status_code == 409


def test_pending_payments_together_cannot_exceed_the_debt(client, api):
    a, b, g = _setup(api)
    url = f"/api/groups/{g['id']}/settlements"
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 300}, headers=b["h"]).status_code == 201
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 300}, headers=b["h"]).status_code == 409  # 600 > 500
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 200}, headers=b["h"]).status_code == 201
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 1}, headers=b["h"]).status_code == 409


def test_joining_a_closed_group_is_refused_but_existing_members_are_unaffected(client, api):
    a, b, g = _setup(api)
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    late = api.user()
    assert client.post(f"/api/join/{g['invite_token']}", headers=late["h"]).status_code == 409
    assert client.post(f"/api/join/{g['invite_token']}", headers=b["h"]).status_code == 200  # already a member
    assert len(api.group_view(g, a)["members"]) == 2


def test_email_invite_has_its_own_working_link_and_marks_acceptance(client, api, db):
    a = api.user()
    g = api.group(a)
    guest = api.user()
    r = client.post(f"/api/groups/{g['id']}/invites", json={"email": guest["email"]}, headers=a["h"])
    link = r.json()["link"]
    assert "/#/join/" in link  # the SPA uses hash routes; a link without '#' would open nothing
    token = link.rsplit("/", 1)[1]
    assert token != g["invite_token"]
    assert client.get(f"/api/join/{token}").json()["name"] == "Trip"
    assert client.post(f"/api/join/{token}", headers=guest["h"]).status_code == 200
    assert len(api.group_view(g, a)["members"]) == 2
    mail = db.scalar(select(Outbox).where(Outbox.to_email == guest["email"], Outbox.kind == "invite"))
    assert link in mail.body
    # re-inviting the same address twice is safe (no 500)
    assert client.post(f"/api/groups/{g['id']}/invites", json={"email": guest["email"]}, headers=a["h"]).status_code == 201


def test_rotating_the_shared_link_revokes_the_old_one_only(client, api):
    a = api.user()
    g = api.group(a)
    guest, other = api.user(), api.user()
    personal = client.post(f"/api/groups/{g['id']}/invites", json={"email": guest["email"]}, headers=a["h"]).json()["link"].rsplit("/", 1)[1]
    new = client.post(f"/api/groups/{g['id']}/invite-link/rotate", headers=a["h"]).json()["invite_token"]
    assert new != g["invite_token"]
    assert client.get(f"/api/join/{g['invite_token']}").status_code == 404
    assert client.post(f"/api/join/{new}", headers=other["h"]).status_code == 200
    assert client.post(f"/api/join/{personal}", headers=guest["h"]).status_code == 200


def test_invites_to_a_closed_group_are_refused(client, api):
    a = api.user()
    g = api.group(a)
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    assert client.post(f"/api/groups/{g['id']}/invites", json={"email": "x@example.com"}, headers=a["h"]).status_code == 409


def test_activity_limit_is_validated(client, api):
    a = api.user()
    g = api.group(a)
    assert client.get(f"/api/groups/{g['id']}/activity?limit=-1", headers=a["h"]).status_code == 422
    assert client.get(f"/api/groups/{g['id']}/activity?limit=0", headers=a["h"]).status_code == 422
    assert client.get(f"/api/groups/{g['id']}/activity?limit=5", headers=a["h"]).status_code == 200
