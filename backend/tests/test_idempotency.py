"""A retry of a request that already went through must return the original result, never a second copy."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models import Expense, Settlement


def _key() -> dict:
    return {"Idempotency-Key": uuid.uuid4().hex}


def _post_expense(client, g, who, payer, amount, ids, headers=None):
    body = {"payer_id": payer["id"], "amount_minor": amount, "title": "t", "category": "food", "spent_on": "2026-10-01", "split": {"type": "equal", "participants": ids}}
    return client.post(f"/api/groups/{g['id']}/expenses", json=body, headers={**who["h"], **(headers or {})})


def test_same_key_creates_one_expense_and_returns_the_original(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    key = _key()
    first = _post_expense(client, g, a, a, 1000, ids, key)
    again = _post_expense(client, g, a, a, 1000, ids, key)
    assert first.status_code == 201 and again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    assert db.scalar(select(func.count()).select_from(Expense).where(Expense.group_id == g["id"])) == 1
    assert api.balances(g, a) == {a["id"]: 500, b["id"]: -500}  # counted once


def test_without_a_key_a_repeat_is_a_new_expense_and_other_keys_do_not_collide(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    _post_expense(client, g, a, a, 1000, ids)
    _post_expense(client, g, a, a, 1000, ids)
    _post_expense(client, g, a, a, 1000, ids, _key())
    _post_expense(client, g, a, a, 1000, ids, _key())
    assert db.scalar(select(func.count()).select_from(Expense).where(Expense.group_id == g["id"])) == 4


def test_a_key_belongs_to_one_user_and_one_kind(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    key = _key()
    assert _post_expense(client, g, a, a, 1000, ids, key).status_code == 201
    other = _post_expense(client, g, b, b, 700, ids, key)  # someone else may use the same string
    assert other.status_code == 201 and other.json()["amount_minor"] == 700
    url = f"/api/groups/{g['id']}/settlements"
    clash = client.post(url, json={"to_user": a["id"], "amount_minor": 100}, headers={**b["h"], **key})
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "idempotency_key_reused"
    assert client.post(url, json={"to_user": a["id"], "amount_minor": 100}, headers={**b["h"], "Idempotency-Key": "short"}).status_code == 422


def test_same_key_records_one_payment(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    url = f"/api/groups/{g['id']}/settlements"
    key = _key()
    first = client.post(url, json={"to_user": a["id"], "amount_minor": 200}, headers={**b["h"], **key})
    again = client.post(url, json={"to_user": a["id"], "amount_minor": 200}, headers={**b["h"], **key})
    assert first.status_code == 201 and again.status_code == 201 and first.json()["id"] == again.json()["id"]
    assert db.scalar(select(func.count()).select_from(Settlement).where(Settlement.group_id == g["id"])) == 1


def test_many_identical_requests_at_once_still_make_one_expense(api, db):
    from concurrent.futures import ThreadPoolExecutor

    a, b = api.user(), api.user()
    g = api.group(a, [b])
    ids = [a["id"], b["id"]]
    key = _key()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _post_expense(api.c, g, a, a, 1000, ids, key), range(8)))
    assert {r.status_code for r in results} == {201}
    assert len({r.json()["id"] for r in results}) == 1
    assert db.scalar(select(func.count()).select_from(Expense).where(Expense.group_id == g["id"])) == 1
