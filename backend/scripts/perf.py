"""Rough latency numbers on a busy group: 12 members, 300 expenses, 20 payments, plus 8 other groups.

Run: cd backend && DATABASE_URL=... uv run python scripts/perf.py   (needs a migrated database; it creates its own users)
"""
import os
import statistics
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare")

from fastapi.testclient import TestClient

from app.main import app


def timed(fn, n=5):
    xs = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    return f"{statistics.median(xs):7.1f} ms (median of {n})"


with TestClient(app) as c:
    tag = uuid.uuid4().hex[:6]
    users = []
    for i in range(12):
        r = c.post("/api/auth/register", json={"email": f"perf{tag}{i}@example.com", "name": f"P{i}", "password": "secret1"}).json()
        users.append({"id": r["user"]["id"], "h": {"Authorization": f"Bearer {r['token']}"}})
    owner = users[0]
    g = c.post("/api/groups", json={"name": "perf", "currency": "USD"}, headers=owner["h"]).json()
    for u in users[1:]:
        c.post(f"/api/join/{g['invite_token']}", headers=u["h"])
    ids = [u["id"] for u in users]
    t0 = time.perf_counter()
    for i in range(300):
        who = users[i % 12]
        amount = 1000 + (i * 37) % 9000
        c.post(f"/api/groups/{g['id']}/expenses", headers=who["h"], json={
            "payer_id": who["id"], "amount_minor": amount, "title": f"e{i}", "category": "food", "spent_on": "2026-10-01",
            "split": {"type": "equal", "participants": ids[: 3 + i % 9]}})
    print(f"creating 300 expenses over HTTP: {time.perf_counter() - t0:.1f} s")
    for k in range(8):
        c.post("/api/groups", json={"name": f"other{k}", "currency": "EUR"}, headers=owner["h"])
    print("group view (12 members, 300 expenses):  ", timed(lambda: c.get(f"/api/groups/{g['id']}", headers=owner["h"])))
    print("expenses page (100 of 300):             ", timed(lambda: c.get(f"/api/groups/{g['id']}/expenses", headers=owner["h"])))
    print("groups list (9 groups):                 ", timed(lambda: c.get("/api/groups", headers=owner["h"])))
    print("balances across all groups:             ", timed(lambda: c.get("/api/me/balances", headers=owner["h"])))
    print("report:                                 ", timed(lambda: c.get(f"/api/groups/{g['id']}/report", headers=owner["h"])))
    print("add one expense:                        ", timed(lambda: c.post(f"/api/groups/{g['id']}/expenses", headers=owner["h"], json={
        "payer_id": owner["id"], "amount_minor": 500, "title": "x", "category": "food", "spent_on": "2026-10-01", "split": {"type": "equal", "participants": ids}})))
