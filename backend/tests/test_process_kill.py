"""The API process dying in the middle of a request, for real: a separate OS process, killed with SIGKILL.

How the 'middle of a request' is made reproducible without touching the application code: the test takes an exclusive lock on
one table in Postgres, so the API's transaction stalls exactly when it first writes to that table, after it has already
written other rows. The process is then killed. Postgres must roll everything back; after a restart the service must work.
"""
from __future__ import annotations

import os
import pathlib
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """The real application as its own OS process (uvicorn), so it can be killed like production would be."""

    def __init__(self):
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None

    def start(self):
        env = {**os.environ, "REMINDER_INTERVAL_SECONDS": "3600"}
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port), "--workers", "1", "--log-level", "warning"],
            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(150):
            try:
                if httpx.get(f"{self.base}/api/health", timeout=1).status_code == 200:
                    return self
            except httpx.TransportError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def kill(self):
        assert self.proc is not None
        self.proc.send_signal(signal.SIGKILL)  # no cleanup handlers, no goodbye: like an OOM kill or a pulled plug
        self.proc.wait(timeout=10)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture()
def server():
    s = Server().start()
    yield s
    s.stop()


@pytest.fixture()
def dbc():
    engine = create_engine(os.environ["DATABASE_URL"])
    yield engine
    engine.dispose()


def _register(base, tag):
    r = httpx.post(f"{base}/api/auth/register", json={"email": f"{tag}{uuid.uuid4().hex[:8]}@example.com", "name": tag, "password": "secret1"}).json()
    return {"id": r["user"]["id"], "h": {"Authorization": f"Bearer {r['token']}"}}


def _setup_group(base):
    a, b = _register(base, "kill-a"), _register(base, "kill-b")
    g = httpx.post(f"{base}/api/groups", json={"name": "K", "currency": "USD"}, headers=a["h"]).json()
    httpx.post(f"{base}/api/join/{g['invite_token']}", headers=b["h"])
    return a, b, g


def _count(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def _wait_until_a_backend_waits_for_a_lock(engine, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _count(engine, "SELECT count(*) FROM pg_locks WHERE NOT granted") > 0:
            return
        time.sleep(0.05)
    raise AssertionError("the request never reached the point where it waits for the lock")


def _kill_in_the_middle(server, engine, locked_table, send):
    """Stall the API's transaction on `locked_table`, kill the process, release the lock. Returns what the client saw."""
    blocker = engine.connect()
    blocker.execute(text(f"LOCK TABLE {locked_table} IN ACCESS EXCLUSIVE MODE"))  # held until we roll back below
    outcome: dict = {}

    def request():
        try:
            outcome["response"] = send()
        except Exception as e:  # noqa: BLE001
            outcome["error"] = e

    t = threading.Thread(target=request)
    t.start()
    _wait_until_a_backend_waits_for_a_lock(engine)
    server.kill()
    t.join(timeout=15)
    blocker.rollback()
    blocker.close()
    time.sleep(1.0)  # let Postgres notice the dead client and drop its abandoned transaction
    return outcome


def test_killed_in_the_middle_of_adding_an_expense_nothing_is_half_saved_and_it_recovers(server, dbc):
    a, b, g = _setup_group(server.base)
    body = {"payer_id": a["id"], "amount_minor": 900, "title": "x", "category": "food", "spent_on": "2026-10-01",
            "split": {"type": "equal", "participants": [a["id"], b["id"]]}}
    key = uuid.uuid4().hex
    outcome = _kill_in_the_middle(
        server, dbc, "notifications",  # the expense row is already written when the API reaches this table
        lambda: httpx.post(f"{server.base}/api/groups/{g['id']}/expenses", json=body, headers={**a["h"], "Idempotency-Key": key}, timeout=20),
    )
    assert "response" not in outcome and isinstance(outcome["error"], httpx.TransportError)  # the client sees a broken connection, not a lie
    assert _count(dbc, "SELECT count(*) FROM expenses WHERE group_id = :g", g=g["id"]) == 0
    assert _count(dbc, "SELECT count(*) FROM expense_shares es JOIN expenses e ON e.id = es.expense_id WHERE e.group_id = :g", g=g["id"]) == 0
    assert _count(dbc, "SELECT count(*) FROM activity WHERE group_id = :g AND kind = 'expense_added'", g=g["id"]) == 0
    assert _count(dbc, "SELECT count(*) FROM idempotency_keys WHERE key = :k", k=key) == 0  # so the retry below is a real first attempt

    restarted = Server().start()  # the "supervisor" restarts the process
    try:
        retry = httpx.post(f"{restarted.base}/api/groups/{g['id']}/expenses", json=body, headers={**a["h"], "Idempotency-Key": key})
        assert retry.status_code == 201
        view = httpx.get(f"{restarted.base}/api/groups/{g['id']}", headers=a["h"]).json()
        assert {m["id"]: m["balance_minor"] for m in view["members"]} == {a["id"]: 450, b["id"]: -450}  # counted exactly once
        assert sum(m["balance_minor"] for m in view["members"]) == 0
    finally:
        restarted.stop()


def test_killed_while_confirming_a_payment_it_stays_pending_and_can_be_confirmed_after_restart(server, dbc):
    a, b, g = _setup_group(server.base)
    httpx.post(f"{server.base}/api/groups/{g['id']}/expenses", headers=a["h"], json={
        "payer_id": a["id"], "amount_minor": 1000, "title": "x", "category": "food", "spent_on": "2026-10-01",
        "split": {"type": "equal", "participants": [a["id"], b["id"]]}})
    s = httpx.post(f"{server.base}/api/groups/{g['id']}/settlements", json={"to_user": a["id"], "amount_minor": 300}, headers=b["h"]).json()
    outcome = _kill_in_the_middle(
        server, dbc, "activity",  # the status is already changed in the transaction when the API writes the feed entry
        lambda: httpx.post(f"{server.base}/api/settlements/{s['id']}/confirm", headers=a["h"], timeout=20),
    )
    assert "error" in outcome
    assert _count(dbc, "SELECT status FROM settlements WHERE id = :i", i=s["id"]) == "pending"  # not 'confirmed' without its feed entry
    restarted = Server().start()
    try:
        assert httpx.post(f"{restarted.base}/api/settlements/{s['id']}/confirm", headers=a["h"]).status_code == 200
        view = httpx.get(f"{restarted.base}/api/groups/{g['id']}", headers=a["h"]).json()
        assert {m["id"]: m["balance_minor"] for m in view["members"]} == {a["id"]: 200, b["id"]: -200}
    finally:
        restarted.stop()


def test_killed_while_closing_a_group_it_stays_open_and_no_summary_mail_exists(server, dbc):
    a, b, g = _setup_group(server.base)
    httpx.post(f"{server.base}/api/groups/{g['id']}/expenses", headers=a["h"], json={
        "payer_id": a["id"], "amount_minor": 1000, "title": "x", "category": "food", "spent_on": "2026-10-01",
        "split": {"type": "equal", "participants": [a["id"], b["id"]]}})
    outcome = _kill_in_the_middle(
        server, dbc, "outbox",  # closing writes the group flag first, then one summary e-mail per member
        lambda: httpx.post(f"{server.base}/api/groups/{g['id']}/close", headers=a["h"], timeout=20),
    )
    assert "error" in outcome
    assert _count(dbc, "SELECT closed FROM groups WHERE id = :g", g=g["id"]) is False  # all or nothing
    assert _count(dbc, "SELECT count(*) FROM outbox WHERE group_id = :g AND kind = 'close_summary'", g=g["id"]) == 0
    restarted = Server().start()
    try:
        assert httpx.post(f"{restarted.base}/api/groups/{g['id']}/close", headers=a["h"]).status_code == 200
        assert _count(dbc, "SELECT count(*) FROM outbox WHERE group_id = :g AND kind = 'close_summary'", g=g["id"]) == 2
    finally:
        restarted.stop()
