from __future__ import annotations

import os
import socket
import threading
import time

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare")
os.environ.setdefault("UPLOAD_DIR", "/tmp/fairshare-test-uploads")
os.environ.setdefault("REMINDER_INTERVAL_SECONDS", "3600")

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def database():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")  # tests run on the real migration, not metadata.create_all
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


_counter = iter(range(1, 10**9))


class Api:
    """Tiny helper around TestClient for readable tests."""

    def __init__(self, client: TestClient):
        self.c = client

    def user(self, name: str = "User") -> dict:
        n = next(_counter)
        r = self.c.post("/api/auth/register", json={"email": f"u{n}@example.com", "name": f"{name}{n}", "password": "secret1"})
        assert r.status_code == 201, r.text
        data = r.json()
        return {"id": data["user"]["id"], "name": data["user"]["name"], "email": data["user"]["email"], "h": {"Authorization": f"Bearer {data['token']}"}}

    def group(self, owner: dict, members: list[dict] = (), currency: str = "USD", remind: int = 7) -> dict:
        r = self.c.post("/api/groups", json={"name": "Trip", "currency": currency, "remind_after_days": remind}, headers=owner["h"])
        assert r.status_code == 201, r.text
        g = r.json()
        for m in members:
            j = self.c.post(f"/api/join/{g['invite_token']}", headers=m["h"])
            assert j.status_code == 200, j.text
        return g

    def expense(self, g: dict, who: dict, payer: dict, amount: int, split: dict, **kw):
        body = {"payer_id": payer["id"], "amount_minor": amount, "title": kw.get("title", "dinner"), "category": kw.get("category", "food"), "spent_on": "2026-10-01", "split": split}
        return self.c.post(f"/api/groups/{g['id']}/expenses", json=body, headers=who["h"])

    def equal(self, ids: list[int]) -> dict:
        return {"type": "equal", "participants": ids}

    def group_view(self, g: dict, who: dict) -> dict:
        r = self.c.get(f"/api/groups/{g['id']}", headers=who["h"])
        assert r.status_code == 200, r.text
        return r.json()

    def balances(self, g: dict, who: dict) -> dict[int, int]:
        return {m["id"]: m["balance_minor"] for m in self.group_view(g, who)["members"]}


@pytest.fixture()
def api(client) -> Api:
    return Api(client)


@pytest.fixture(scope="session")
def live_server():
    """A real uvicorn server on a free port, for tests that need two simultaneous HTTP clients."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
