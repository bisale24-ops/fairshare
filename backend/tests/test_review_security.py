"""Findings from the independent review: tokens, throttling, input bounds, receipts."""
from __future__ import annotations

import os
from datetime import timedelta

from sqlalchemy import select, update

from app import config
from app.api.misc import router as misc_router
from app.models import AuthToken, now_utc

PNG = b"\x89PNG\r\n\x1a\n"


def test_query_token_is_accepted_only_by_the_stream(client, api):
    u = api.user()
    token = u["h"]["Authorization"].split()[1]
    assert client.get(f"/api/groups?access_token={token}").status_code == 401  # ordinary routes ignore it
    assert client.get("/api/groups", headers=u["h"]).status_code == 200


def test_stream_does_not_hold_a_pooled_db_session_for_its_lifetime():
    def walk(dep):
        for sub in dep.dependencies:
            yield sub.call
            yield from walk(sub)

    route = next(r for r in misc_router.routes if getattr(r, "path", "") == "/api/stream")
    names = {getattr(c, "__name__", "") for c in walk(route.dependant)}
    assert "get_db" not in names and "stream_user" in names


def test_tokens_expire_and_logout_revokes(client, api, db):
    u = api.user()
    old = db.scalar(select(AuthToken).where(AuthToken.user_id == u["id"]))
    db.execute(update(AuthToken).where(AuthToken.user_id == u["id"]).values(created_at=now_utc() - timedelta(days=config.TOKEN_TTL_DAYS + 1)))
    db.commit()
    assert client.get("/api/auth/me", headers=u["h"]).status_code == 401
    fresh = client.post("/api/auth/login", json={"email": u["email"], "password": "secret1"}).json()
    h = {"Authorization": f"Bearer {fresh['token']}"}
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert old is not None


def test_repeated_wrong_passwords_are_throttled_per_address(client, api):
    u = api.user()
    for _ in range(config.LOGIN_MAX_FAILURES):
        assert client.post("/api/auth/login", json={"email": u["email"], "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "wrong-pass"}).status_code == 429
    assert client.post("/api/auth/login", json={"email": u["email"], "password": "secret1"}).status_code == 429
    other = api.user()  # someone else is not affected
    assert client.post("/api/auth/login", json={"email": other["email"], "password": "secret1"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"}).status_code == 401


def test_split_input_is_bounded_and_validated(client, api):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    url = f"/api/groups/{g['id']}/expenses"
    body = {"payer_id": a["id"], "amount_minor": 1000, "spent_on": "2026-10-01"}
    bad = [
        {"type": "shares", "weights": {str(a["id"]): 3_000_000_000, str(b["id"]): 1}},  # would overflow the DB column
        {"type": "shares", "weights": {str(a["id"]): 0}},
        {"type": "equal", "participants": [a["id"], a["id"], b["id"]]},  # duplicates are an error, not silently merged
        {"type": "equal", "participants": list(range(1, 202))},  # too many
        {"type": "exact", "amounts": {str(2**40): 1000}},  # id out of range
        {"type": "exact", "amounts": {str(a["id"]): -5, str(b["id"]): 1005}},
    ]
    for split in bad:
        assert client.post(url, json={**body, "split": split}, headers=a["h"]).status_code == 422, split
    ok = client.post(url, json={**body, "split": {"type": "equal", "participants": [a["id"], b["id"]]}}, headers=a["h"])
    assert ok.status_code == 201


def _expense(api, a):
    g = api.group(a)
    e = api.expense(g, a, a, 1000, api.equal([a["id"]])).json()
    return g, e, f"/api/groups/{g['id']}/expenses/{e['id']}/receipt"


def test_receipt_type_comes_from_the_bytes_not_from_the_client(client, api):
    a = api.user()
    g, e, url = _expense(api, a)
    html = b"<html><script>alert(1)</script></html>"
    assert client.post(url, files={"file": ("x.png", html, "image/png")}, headers=a["h"]).status_code == 415
    assert client.post(url, files={"file": ("x.pdf", html, "application/pdf")}, headers=a["h"]).status_code == 415
    # a genuine PNG is accepted even if the client mislabels it
    assert client.post(url, files={"file": ("page.html", PNG + b"x", "text/html")}, headers=a["h"]).status_code == 200
    got = client.get(url, headers=a["h"])
    assert got.headers["content-type"] == "image/png"  # not guessed from the user-controlled name 'page.html'
    assert got.headers["content-disposition"].startswith("attachment")
    assert got.headers["x-content-type-options"] == "nosniff"


def test_receipt_replace_removes_old_file_and_closed_group_is_frozen(client, api):
    a = api.user()
    g, e, url = _expense(api, a)
    client.post(url, files={"file": ("a.png", PNG + b"1", "image/png")}, headers=a["h"])
    before = set(os.listdir(config.UPLOAD_DIR))
    client.post(url, files={"file": ("b.png", PNG + b"2", "image/png")}, headers=a["h"])
    after = set(os.listdir(config.UPLOAD_DIR))
    assert len(after - before) == 1 and len(before - after) == 1  # one new file, the old one is gone
    client.post(f"/api/groups/{g['id']}/close", headers=a["h"])
    assert client.post(url, files={"file": ("c.png", PNG + b"3", "image/png")}, headers=a["h"]).status_code == 409
