from __future__ import annotations

import os

from app import config

PNG = b"\x89PNG\r\n\x1a\n"


def _body(api, who_pays, amount, ids, **extra):
    return {"payer_id": who_pays["id"], "amount_minor": amount, "title": "t", "category": "food", "spent_on": "2026-10-01", "split": api.equal(ids), **extra}


# ---- payment recorded by the person who RECEIVED the money --------------------------------------------------------

def test_the_creditor_can_record_cash_received_and_the_debtor_confirms(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))   # b owes a 500
    url = f"/api/groups/{g['id']}/settlements"
    s = client.post(url, json={"from_user": b["id"], "amount_minor": 300}, headers=a["h"]).json()
    assert (s["from_user"], s["to_user"], s["created_by"], s["confirmer"]) == (b["id"], a["id"], a["id"], b["id"])
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 403  # not by the one who recorded it
    assert any("paid them" in n["text"] for n in client.get("/api/notifications", headers=b["h"]).json())
    assert client.post(f"/api/settlements/{s['id']}/confirm", headers=b["h"]).status_code == 200
    assert api.balances(g, a) == {a["id"]: 200, b["id"]: -200}


def test_settlement_direction_must_be_exactly_one(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    url = f"/api/groups/{g['id']}/settlements"
    assert client.post(url, json={"amount_minor": 100}, headers=a["h"]).status_code == 422
    assert client.post(url, json={"to_user": b["id"], "from_user": b["id"], "amount_minor": 100}, headers=a["h"]).status_code == 422
    assert client.post(url, json={"from_user": a["id"], "amount_minor": 100}, headers=a["h"]).status_code == 422  # from myself


# ---- no lost updates ------------------------------------------------------------------------------------------------

def test_stale_edit_is_rejected_with_a_conflict(client, api):
    a = api.user()
    b = api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    e = api.expense(g, a, a, 1000, api.equal(ids)).json()
    assert e["version"] == 1
    url = f"/api/groups/{g['id']}/expenses/{e['id']}"
    first = client.put(url, json=_body(api, a, 1200, ids, version=1), headers=a["h"])
    assert first.status_code == 200 and first.json()["version"] == 2
    stale = client.put(url, json=_body(api, a, 1300, ids, version=1), headers=a["h"])
    assert stale.status_code == 409 and "changed by someone else" in stale.json()["detail"]["message"]
    assert client.put(url, json=_body(api, a, 1300, ids, version=2), headers=a["h"]).status_code == 200
    assert client.put(url, json=_body(api, a, 1400, ids), headers=a["h"]).status_code == 200  # version is optional for API users


# ---- leaving, removing, deleting ---------------------------------------------------------------------------------

def test_leave_only_when_settled_and_old_expenses_keep_names(client, api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])
    ids = [a["id"], b["id"], c["id"]]
    e = api.expense(g, a, a, 900, api.equal(ids)).json()
    leave = f"/api/groups/{g['id']}/leave"
    assert client.post(leave, headers=c["h"]).status_code == 409  # c owes 300
    s = client.post(f"/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 300}, headers=c["h"]).json()
    assert client.post(leave, headers=c["h"]).status_code == 409  # a payment is waiting for an answer
    client.post(f"/api/settlements/{s['id']}/confirm", headers=a["h"])
    assert client.post(leave, headers=c["h"]).status_code == 200
    assert client.get(f"/api/groups/{g['id']}", headers=c["h"]).status_code == 404  # no longer a member
    assert len(api.group_view(g, a)["members"]) == 2
    listed = client.get(f"/api/groups/{g['id']}/expenses", headers=a["h"]).json()
    assert {s["name"] for s in listed[0]["shares"]} == {a["name"], b["name"], c["name"]}  # names survive the departure
    assert sum(api.balances(g, a).values()) == 0
    body = _body(api, a, 1200, ids, version=1)  # editing may still keep the person who left in that expense
    assert client.put(f"/api/groups/{g['id']}/expenses/{e['id']}", json=body, headers=a["h"]).status_code == 200


def test_last_member_cannot_leave_and_only_the_creator_removes_people(client, api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])
    assert client.delete(f"/api/groups/{g['id']}/members/{c['id']}", headers=b["h"]).status_code == 403
    assert client.delete(f"/api/groups/{g['id']}/members/{a['id']}", headers=a["h"]).status_code == 422  # use leave
    r = client.delete(f"/api/groups/{g['id']}/members/{c['id']}", headers=a["h"])
    assert r.status_code == 200 and len(r.json()["members"]) == 2
    assert any("removed" in n["text"] for n in client.get("/api/notifications", headers=c["h"]).json())
    assert client.post(f"/api/groups/{g['id']}/leave", headers=b["h"]).status_code == 200
    assert client.post(f"/api/groups/{g['id']}/leave", headers=a["h"]).status_code == 409  # the last one


def test_removing_someone_who_still_owes_is_refused(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    assert client.delete(f"/api/groups/{g['id']}/members/{b['id']}", headers=a["h"]).status_code == 409


def test_delete_group_creator_only_and_files_go(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    e = api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]])).json()
    url = f"/api/groups/{g['id']}/expenses/{e['id']}/receipt"
    client.post(url, files={"file": ("r.png", PNG + b"1", "image/png")}, headers=a["h"])
    files = set(os.listdir(config.UPLOAD_DIR))
    assert client.delete(f"/api/groups/{g['id']}", headers=b["h"]).status_code == 403
    assert client.delete(f"/api/groups/{g['id']}", headers=a["h"]).status_code == 409  # open and has expenses
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    assert client.delete(f"/api/groups/{g['id']}", headers=a["h"]).status_code == 200
    assert client.get(f"/api/groups/{g['id']}", headers=b["h"]).status_code == 404
    assert len(files - set(os.listdir(config.UPLOAD_DIR))) == 1
    empty = api.group(a)  # an empty open group can be deleted straight away
    assert client.delete(f"/api/groups/{empty['id']}", headers=a["h"]).status_code == 200


def test_deleting_an_expense_removes_its_receipt_file(client, api):
    a = api.user()
    g = api.group(a)
    e = api.expense(g, a, a, 1000, api.equal([a["id"]])).json()
    url = f"/api/groups/{g['id']}/expenses/{e['id']}/receipt"
    client.post(url, files={"file": ("r.png", PNG + b"x", "image/png")}, headers=a["h"])
    before = set(os.listdir(config.UPLOAD_DIR))
    assert client.delete(f"/api/groups/{g['id']}/expenses/{e['id']}", headers=a["h"]).status_code == 200
    assert len(before - set(os.listdir(config.UPLOAD_DIR))) == 1


# ---- lists and notifications -------------------------------------------------------------------------------------

def test_lists_are_paginated(client, api):
    a = api.user()
    g = api.group(a)
    for i in range(5):
        api.expense(g, a, a, 100 + i, api.equal([a["id"]]), title=f"e{i}")
    url = f"/api/groups/{g['id']}/expenses"
    assert len(client.get(url, headers=a["h"]).json()) == 5
    page = client.get(f"{url}?limit=2&offset=2", headers=a["h"]).json()
    assert len(page) == 2
    assert client.get(f"{url}?limit=0", headers=a["h"]).status_code == 422
    assert client.get(f"{url}?limit=500", headers=a["h"]).status_code == 422


def test_notifications_can_be_read_one_by_one(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    api.expense(g, a, a, 2000, api.equal([a["id"], b["id"]]))
    notes = client.get("/api/notifications", headers=b["h"]).json()
    assert len(notes) == 2 and not any(n["read"] for n in notes)
    assert client.post(f"/api/notifications/{notes[0]['id']}/read", headers=b["h"]).status_code == 200
    after = {n["id"]: n["read"] for n in client.get("/api/notifications", headers=b["h"]).json()}
    assert after == {notes[0]["id"]: True, notes[1]["id"]: False}
    assert client.post(f"/api/notifications/{notes[1]['id']}/read", headers=a["h"]).status_code == 404  # not yours


def test_when_the_creator_leaves_the_longest_member_takes_over(client, api):
    a, b, c = api.user(), api.user(), api.user()
    g = api.group(a, [b, c])  # b joined before c
    assert api.group_view(g, a)["created_by"] == a["id"]
    assert client.post(f"/api/groups/{g['id']}/leave", headers=a["h"]).status_code == 200
    view = api.group_view(g, b)
    assert view["created_by"] == b["id"]
    feed = client.get(f"/api/groups/{g['id']}/activity", headers=b["h"]).json()
    assert {f["kind"] for f in feed[:2]} == {"new_owner", "left"}
    # the new owner really has the rights
    assert client.delete(f"/api/groups/{g['id']}/members/{c['id']}", headers=b["h"]).status_code == 200
    assert client.delete(f"/api/groups/{g['id']}/members/{b['id']}", headers=c["h"]).status_code == 404  # c is gone
