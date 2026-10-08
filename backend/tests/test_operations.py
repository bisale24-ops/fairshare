"""Things that only matter when the system runs for real: the reminder timer, a database that goes away, a crash mid-operation."""
from __future__ import annotations

import asyncio
import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text, update

from app import main
from app.main import app
from app.models import DebtState, Outbox, now_utc


def test_the_reminder_timer_really_runs_and_sends_mail(client, api, db):
    a, b = api.user(), api.user()
    g = api.group(a, [b], remind=1)
    api.expense(g, a, a, 1000, api.equal([a["id"], b["id"]]))
    db.execute(update(DebtState).where(DebtState.group_id == g["id"]).values(since=now_utc() - timedelta(days=3)))
    db.commit()

    async def run_briefly():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(main._reminder_loop(interval=0.05), timeout=1.5)

    asyncio.run(run_briefly())
    db.expire_all()
    mails = db.scalars(select(Outbox).where(Outbox.group_id == g["id"], Outbox.kind == "reminder")).all()
    assert len(mails) == 1 and mails[0].to_email == b["email"]


def test_the_timer_is_started_with_the_app_and_stopped_with_it():
    with TestClient(app) as c:
        c.get("/api/health")
        task = app.state.reminder_task
        assert not task.done()
    assert task.cancelled() or task.done()


def test_requests_survive_the_database_dropping_every_connection(client, api):
    u = api.user()
    assert client.get("/api/groups", headers=u["h"]).status_code == 200  # warm the pool
    killer = create_engine(os.environ["DATABASE_URL"])
    with killer.begin() as conn:
        conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"))
    killer.dispose()
    assert client.get("/api/groups", headers=u["h"]).status_code == 200  # pool_pre_ping reconnects instead of failing
    g = api.group(u)
    assert api.expense(g, u, u, 500, api.equal([u["id"]])).status_code == 201


def test_a_crash_in_the_middle_of_adding_an_expense_leaves_nothing_behind(api, monkeypatch):
    a, b = api.user(), api.user()
    g = api.group(a, [b])
    import app.api.expenses as expenses_module

    def boom(*args, **kwargs):
        raise RuntimeError("process died here")

    monkeypatch.setattr(expenses_module, "notify", boom)
    with TestClient(app, raise_server_exceptions=False) as crashing:
        body = {"payer_id": a["id"], "amount_minor": 900, "title": "x", "category": "food", "spent_on": "2026-10-01", "split": api.equal([a["id"], b["id"]])}
        assert crashing.post(f"/api/groups/{g['id']}/expenses", json=body, headers=a["h"]).status_code == 500
    monkeypatch.undo()
    assert api.c.get(f"/api/groups/{g['id']}/expenses", headers=a["h"]).json() == []  # not half-saved
    assert api.balances(g, a) == {a["id"]: 0, b["id"]: 0}
    kinds = [f["kind"] for f in api.c.get(f"/api/groups/{g['id']}/activity", headers=a["h"]).json()]
    assert "expense_added" not in kinds  # no feed entry either
