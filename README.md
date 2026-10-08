# Fairshare — shared expenses (Mad Devs test, case 6)

Groups, expenses split three ways, live balances, minimal transfers, settlements confirmed by the receiver,
activity feed, reminders and closing a group with a report. React + FastAPI + PostgreSQL.

## Run it

```bash
docker compose up --build        # http://localhost:8080
```

Needs only Docker. The database migrates itself on start. E-mail is a stub: every message the system would send
is saved to the `outbox` table, logged, and shown in the app under **✉ Письма** (top right).

Two people at once: open the app in two browser tabs. Each tab is its own session (the token lives in `sessionStorage`),
so register two different users, share the group link from *Настройки*, and watch one tab update from the other.

Local development:

```bash
docker run -d --name fairshare-pg -e POSTGRES_USER=fairshare -e POSTGRES_PASSWORD=fairshare -e POSTGRES_DB=fairshare -p 5433:5432 postgres:16-alpine
cd backend && uv sync && DATABASE_URL=postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare uv run alembic upgrade head \
  && DATABASE_URL=postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare uv run uvicorn app.main:app --reload   # :8000
cd frontend && npm install && npm run dev                                                                                  # :5173, proxies /api
```

## Tests (the proof)

```bash
cd backend && DATABASE_URL=postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare uv run pytest -q   # 45 tests
cd frontend && npm test && npm run build                      # 5 unit tests + type-check + build
cd frontend && BASE_URL=http://localhost:8080 npm run e2e      # two browsers, real UI (needs Google Chrome + the running stack)
cd frontend && BASE_URL=http://localhost:8080 node e2e/review-fixes.mjs   # e-mail invite link joins; failed receipt never duplicates an expense
cd frontend && BASE_URL=http://localhost:8080 node e2e/mobile.mjs   # 375px phone: no horizontal scroll on any screen
```

CI (`.github/workflows/ci.yml`) runs: backend tests against a Postgres service, frontend tests and build, and
`docker compose up --build --wait`, a smoke test through the public port and the browser e2e below.

**Browser end-to-end** (`frontend/e2e/two-people.mjs`, Playwright driving the installed Chrome): two separate browser
contexts act as two people. Alice creates a group; Bob joins by her link and adds 10.01; Alice's page, never reloaded,
shows −5,01 and an unread notification; Alice pays 2.00; the payment stays pending and changes no balance until Bob
confirms; then both see ∓3,01; Alice closes the group and Bob can no longer add expenses. Screenshots from that run:
`docs/screenshots/`.

| Requirement from the case | Where it is proven |
|---|---|
| Shares always add up to the expense; fixed leftover-cent rule | `tests/test_money.py` (Hypothesis: any total, any weights) and `test_equal_split_keeps_every_cent…` |
| Minimal set of transfers, not everyone-to-everyone | `test_transfer_count_is_optimal` compares with a brute-force reference; `test_group_view_proposes_minimal_transfers` |
| Edit/delete recomputes everything, including settlements | `test_edit_and_delete_recompute_everything_including_settlements` |
| Payment counts only after the receiver confirms; pending is visible to both | `test_settlement_rules` |
| Notification when an expense with me appears or is edited | `test_notifications_on_expense_with_me_and_on_edit` |
| Reminder: after the term, at most weekly, never if paid | `test_reminders_after_term_once_a_week_never_when_paid` (clock is injected) |
| Two simultaneous expenses are both counted; balances sum to zero | `test_two_concurrent_expenses_…` (30 expenses from 12 threads) |
| Closing: no new expenses, summary e-mail to everyone, reopen | `test_closed_group_blocks_expenses_sends_summary_and_reopens` |
| Updates reach every open client immediately | `tests/test_live.py` (two real HTTP clients) and the browser e2e (two browsers) |
| Balance across all groups together | `test_balances_across_all_groups_are_netted_per_person_and_currency` |

The tests run on the real Alembic migration, not on `create_all`. I also broke the code on purpose to check the tests
notice (see DEVLOG, 2026-10-09 01:00): two of three mutants were caught; the third is an equivalent mutant, explained there.

## How it works (decisions)

- **Money** is integer minor units (cents) end to end. The UI parses `12.34` with a regex, never `parseFloat`.
- **Leftover cents.** Shares use the largest-remainder method; leftover cents go to the largest fractional remainder,
  ties to the lowest user id. For an equal split the lowest ids get the extra cent, always.
- **Balances are never stored.** They are recomputed from expenses, shares and confirmed settlements on every read
  (`ledger.compute_balances`), so editing or deleting an old expense cannot leave stale numbers. Each expense adds `+amount`
  to the payer and subtracts shares that sum to `amount`, so group balances always sum to zero.
- **Minimal transfers.** With `n` non-zero balances the fewest transfers is `n − k`, where `k` is the most disjoint zero-sum
  subsets. That is NP-hard in general, so up to 12 people with a non-zero balance it is solved exactly (bitmask DP, O(3^n),
  about 0.05 s at 12), beyond that by greedy matching (at most `n − 1` transfers).
- **Settlements.** The debtor records a payment (full or partial); only the receiver can confirm or reject it. The amount
  cannot exceed what the payer owes or what the receiver is owed, and payments still waiting for confirmation between the
  same two people count against that limit. Pending payments show to both but do not change balances.
- **A closed group is frozen.** No expenses, no new or confirmed payments, no new members, no receipts: the summary e-mail
  must stay true. A group cannot be closed while payments are pending. Reopen it to continue.
- **Who may do what.** Any member can add expenses (also on behalf of someone else), invite, close and reopen. Only the
  person who added an expense or paid for it can edit or delete it.
- **Edited-down expenses.** If an edit or delete makes an earlier confirmed payment bigger than the debt, the balance
  simply flips (it stays exact), the response carries `warnings`, the UI shows who overpaid and by how much, and the feed
  records `settlement_overpaid`.
- **Concurrency.** Creating, editing and deleting an expense, and closing the group, take a row lock on the group, so a
  closing group cannot race a new expense. Independent expenses never conflict.
- **Reminders.** A member who has been continuously in debt longer than the group's term gets an e-mail with the amount and
  recipients (from the minimal plan), at most once per 7 days; paying clears the debt state, so no reminder follows.
  A background loop in the API process runs every 60 s (`REMINDER_INTERVAL_SECONDS`). The weekly limit holds even if a
  debt is paid and returns the next day, and closed time does not count towards the term (reopening restarts the clock).
  Each group is processed under its row lock.
- **Live updates** use Server-Sent Events (`/api/stream`): after each change the server tells every member's open clients,
  and screens refetch. The hub is in-process, so the API runs one worker. To scale out, replace `events.publish` with
  Postgres LISTEN/NOTIFY.
- **Auth.** E-mail + password (scrypt), opaque random bearer tokens (SHA-256 hashed in the DB), 30-day expiry, logout
  revokes. Eight wrong passwords in five minutes from one address for one e-mail give 429. Only the live stream accepts the
  token as `?access_token=` (`EventSource` cannot send headers); every other route ignores it. The stream uses its own
  short DB session so open tabs do not exhaust the connection pool.
- **Invites.** The group link is shared and can be rotated (the old one stops working). An e-mail invite carries its own
  personal link, which keeps working after the shared link is rotated.
- **Receipts:** PNG/JPEG/WebP/PDF up to 5 MB. The type is detected from the file's own bytes (the browser-declared type
  is not trusted), stored in a volume, served to members only as an attachment with `nosniff`; replacing deletes the old file.
- **Input bounds:** at most 200 participants per split, weights 1..1 000 000, ids in the 32-bit range, duplicates are a 422.

## Honest status

Works and is tested: everything in the table above, plus the fixes from an independent read-only review (below).

**Independent review.** Three read-only reviewers (business logic, security/concurrency, frontend) went through the repo;
I confirmed each finding before fixing it, and each fix has a test that fails without it (tests in
`backend/tests/test_review_*.py`, `frontend/e2e/review-fixes.mjs`; hand-made mutants in DEVLOG). Fixed: payments and joins
on a closed group, unserialised join, e-mail invite links that opened nothing, token in any URL and no expiry, stream
holding a pooled DB session, unbounded split input (DB-overflow 500), receipt type trusted from the client, reminder
weekly cap lost on a paid debt, closed time counted as debt time, a failed receipt upload leading to a duplicate expense,
stale data when switching groups, missed events after a dropped connection, session expiry handling.

Known gaps, not hidden:
- The browser e2e covers happy paths (create, join, add, pay, confirm, close; e-mail invite; failed receipt; over-payment warning); editing,
  deleting and reminders in the browser are covered at API level only. The e2e scripts were flaky once and are fixed:
  parallel runs shared one `Date.now()` e-mail, and a status text matched both the status tag and the live banner. They now
  use unique ids and exact locators; 30 of 30 runs passed with two scripts running at the same time.
- Live updates need a single API worker (in-process hub). No password reset, no e-mail verification (e-mail is a stub, so the
  mailbox for an address is whoever registered it first). Registration reveals whether an e-mail exists (409).
- Throttling is in memory, per process.
- Currencies are assumed to have two decimal places (JPY and similar would need a per-currency exponent).
- "Who owes you" across all groups is derived from each group's minimal plan, so counterparties can change after an edit;
  the totals are exact, the attribution to a person is a view of the plan.
- Any member can close, reopen or change a group's settings (the case does not say who may).
- The UI is Russian only. There are no frontend component tests, only the money helpers and error formatting.
- Compose passwords are development defaults; there is no TLS termination (put a proxy in front for real use).

## Next steps (what I would do next)

More browser e2e paths (edit/delete, reminders); LISTEN/NOTIFY hub and multiple workers; per-currency decimals;
password reset and e-mail verification; real SMTP transport behind the existing `send_email` seam.

## Made with

Written with Claude Code (Claude Sonnet 5.5). Nothing is copied from a template or generator: Vite's scaffold was not
used (files are hand-written), the Alembic migration was produced with `alembic revision --autogenerate`, and the UI
colors come from the Notion style on styles.refero.design. See `docs/PROMPTS.md` and `DEVLOG.md`.
