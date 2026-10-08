# Dev log

Times are local (Bishkek, UTC+6). Agent: Claude Code (Claude Sonnet 5.5) driven by me; see docs/PROMPTS.md.

- 2026-10-08 23:35 — Chose case 6. Repo created. Read task, wrote docs/TASK.md.
- 2026-10-08 23:55 — Domain core (integer cents, largest-remainder splits, exact min-transfers DP) + Hypothesis tests green.
- 2026-10-09 00:40 — Backend: FastAPI + SQLAlchemy 2 + PostgreSQL 16, Alembic migration 0001, auth (scrypt + opaque tokens), groups/invites, expenses (equal/shares/exact), receipts, settlements with receiver confirmation, activity feed, notifications, e-mail stub (outbox), reminders, SSE live stream, close/reopen with report.
- 2026-10-09 00:55 — 24 pytest tests green on real Postgres through the Alembic migration (incl. 30 concurrent expenses, live SSE with two HTTP clients, reminder timing with injected clock).
- 2026-10-09 01:00 — Mutation check by hand: dropping confirmed settlements and dropping leftover cents are both caught. Removing the `balance >= 0` guard in reminders is NOT caught: it is redundant on purpose, because refresh_debt_state() already deletes the debt row when a balance stops being negative (equivalent mutant).
- Decision: the SSE stream takes `?access_token=` because EventSource cannot send headers; the token is the same opaque bearer token.
