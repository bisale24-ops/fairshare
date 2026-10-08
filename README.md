# Fairshare — shared expenses (Mad Devs test, case 6)

[![ci](https://github.com/bisale24-ops/fairshare/actions/workflows/ci.yml/badge.svg)](https://github.com/bisale24-ops/fairshare/actions/workflows/ci.yml)

Groups, expenses split three ways, live balances, minimal transfers, payments confirmed by the other side, activity feed,
reminders, closing a group with a report, leaving and removing members. React + FastAPI + PostgreSQL.

## Run it

```bash
docker compose up --build        # http://localhost:8080
```

Needs only Docker. The database migrates itself on start. E-mail is a stub: every message the system would send
is saved to the `outbox` table, logged, and shown in the app under **✉ Письма** (top right; `DEV_MAILBOX=0` switches it off).

Two people at once: open the app in two browser tabs. Each tab is its own session (the token lives in `sessionStorage`),
so register two different users, share the group link from *Настройки*, and watch one tab update from the other.

Local development:

```bash
docker run -d --name fairshare-pg -e POSTGRES_USER=fairshare -e POSTGRES_PASSWORD=fairshare -e POSTGRES_DB=fairshare -p 5433:5432 postgres:16-alpine
export DATABASE_URL=postgresql+psycopg://fairshare:fairshare@localhost:5433/fairshare
cd backend && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload   # :8000
cd frontend && npm install && npm run dev                                                      # :5173, proxies /api
```

## Tests (the proof)

```bash
cd backend && uv run pytest -q --cov=app          # 81 tests, ~95 % of lines (needs the Postgres above)
cd frontend && npm run coverage && npm run build  # 31 tests (components, hooks, money, errors, reliability), type-check, build
cd frontend && BASE_URL=http://localhost:8080 npm run e2e:all   # 4 browser scenarios, needs Google Chrome + the running stack
cd frontend && BACKEND_CONTAINER=<api container> npm run e2e:restart   # kills the API container while two people work, then the process inside it
cd backend && uv run python scripts/perf.py       # latency numbers on a busy group
```

CI (`.github/workflows/ci.yml`) runs on every push: the backend tests against a Postgres service, the frontend tests and build,
and `docker compose up --build --wait` + a smoke test + all browser scenarios, including the ones that kill the API. It is green
on GitHub's machines. Its first run found a real flaw in one of my tests (a test proxy that read an answer in a single `recv`),
fixed in the next commit; that is why the history has a failed run.

| Requirement from the case | Where it is proven |
|---|---|
| Shares always add up to the expense; fixed leftover-cent rule | `tests/test_money.py` (Hypothesis: any total, any weights); `test_equal_split_keeps_every_cent…` |
| Minimal set of transfers, not everyone-to-everyone | `test_transfer_count_is_optimal` against a brute-force reference; `test_group_view_proposes_minimal_transfers` |
| Edit/delete recomputes everything, including payments | `test_edit_and_delete_recompute_everything_including_settlements` |
| A payment counts only after the other side confirms; pending is visible to both | `test_settlement_rules`, `test_the_creditor_can_record_cash_received_and_the_debtor_confirms` |
| Notification when an expense with me appears or is edited | `test_notifications_on_expense_with_me_and_on_edit` |
| Reminder: after the term, at most weekly, never if paid | `test_reminders_*` (injected clock), `test_the_reminder_timer_really_runs_and_sends_mail` |
| Two simultaneous expenses are both counted; balances sum to zero | `test_two_concurrent_expenses_…` (30 expenses from 12 threads) |
| Closing: no new expenses, summary e-mail to everyone, reopen | `test_closed_group_*` |
| Updates reach every open client immediately | `tests/test_live.py` (two real HTTP clients) and `e2e/two-people.mjs` (two browsers) |
| Balance across all groups together | `test_balances_across_all_groups_are_netted_per_person_and_currency` |

The tests run on the real Alembic migrations, not on `create_all`. I broke the code on purpose several times to check that
the tests notice (DEVLOG): every behaviour mutant was caught except one equivalent mutant, explained there.

**Browser scenarios** (`frontend/e2e/`, Playwright driving the installed Chrome, separate browser contexts as separate people):
`two-people` (create, join, add 10.01, live update without reload, partial payment pending then confirmed, close),
`review-fixes` (e-mail invite link joins; a failed receipt never duplicates an expense; a bystander cannot delete; over-payment
warning), `membership` (cash received recorded by the creditor, leaving with a Russian error while in debt, leaving when settled,
deleting a group), `mobile` (375 px: no horizontal scroll on any screen). Screenshots: `docs/screenshots/`. Run 30 times in
parallel without a failure after the flakiness was fixed (DEVLOG).

## When the API process dies

Tested for real, not assumed (`backend/tests/test_process_kill.py`, `test_lost_response.py`, `frontend/e2e/restart.mjs`):

- **Killed in the middle of a write.** The test starts the API as its own OS process, stalls its transaction on a locked table
  after other rows were already written, and sends `SIGKILL`. Postgres rolls everything back: no half-saved expense, no payment
  confirmed without its feed entry, no group closed without its summary e-mails (three scenarios). A restart serves the retry.
  Early-commit mutants of the code are caught by these tests.
- **Committed, but the answer never arrived.** A TCP proxy swallows the response after the server finished. Without protection a
  retry creates a second expense (the test shows this on purpose); with the `Idempotency-Key` that the web client sends for every
  expense and payment, the retry returns the original. Keys are stored in the same transaction as the expense, are scoped to the
  user, and are purged after a week.
- **What the person sees.** In a real browser: while the API is down, a clear message in Russian (not "Failed to fetch"), the form
  keeps what was typed, nobody is logged out; when it is back, pressing the button once more creates exactly one expense and the
  other person's page, never reloaded, catches up by itself (the live stream reconnects with growing delays; only a 401 ends a
  session). A killed container is tested with people in a browser; a process dying inside the container is tested separately
  (`e2e/supervisor.mjs`): Docker's restart policy (`restart: unless-stopped`) brings it back by itself, healthy again in 1 to 5 s.
- **Deployment details that make this work**, each pinned by a test: nginx re-resolves the API's address (otherwise it keeps the
  old one after a restart) and gives up on a dead address in 3 s (not 60); requests time out in the browser after 20 s; the
  image stops live streams within 5 s on shutdown.

## Performance (measured, `scripts/perf.py`)

12 members, 300 expenses, 9 groups, local Postgres, one worker, median of 5:

| request | time |
|---|---|
| group view (balances + minimal transfers) | 25 ms |
| expenses page (100 of 300) | 28 ms |
| list of 9 groups | 58 ms |
| balances across all groups | 66 ms |
| report | 57 ms |
| add an expense | 53 ms |

Balances are computed once per request and the minimal-transfers result is cached by the balances themselves (before this:
group view 65 ms, all-groups 195 ms). Lists take `limit`/`offset`. Screens refetch only for the group that changed.
This is a single-machine measurement, not a load test.

## How it works (decisions)

- **Money** is integer minor units end to end. Currencies are validated ISO 4217 codes with their number of minor digits
  (JPY 0, USD 2, KWD 3); the table is generated for the frontend and a test keeps both copies identical.
- **Leftover cents.** Shares use the largest-remainder method; leftover cents go to the largest fractional remainder,
  ties to the lowest user id. For an equal split the lowest ids get the extra cent, always.
- **Balances are never stored.** They are recomputed from expenses, shares and confirmed payments on every read
  (`ledger.compute_balances`), so editing or deleting an old expense cannot leave stale numbers. Each expense adds `+amount`
  to the payer and subtracts shares that sum to `amount`, so group balances always sum to zero.
- **Minimal transfers.** With `n` non-zero balances the fewest transfers is `n − k`, where `k` is the most disjoint zero-sum
  subsets. That is NP-hard in general, so up to 12 people with a non-zero balance it is solved exactly (bitmask DP, O(3^n),
  about 0.05 s at 12), beyond that by greedy matching (at most `n − 1` transfers).
- **Payments.** Either side records a payment (the debtor "I paid", the creditor "I was paid" in cash); only the other side
  can confirm or reject it. The amount cannot exceed what the payer owes or the receiver is owed, and payments still waiting
  between the same two people count against that limit. Pending payments show to both but change no balance.
- **Edited-down expenses.** If an edit or delete makes an earlier confirmed payment bigger than the debt, the balance simply
  flips (it stays exact), the response carries `warnings`, the UI shows who overpaid, and the feed records `settlement_overpaid`.
- **Edit conflicts.** Expenses carry a `version`; an edit that echoes a stale version gets a 409 instead of overwriting.
- **A closed group is frozen.** No expenses, no new or confirmed payments, no new members, no receipts: the summary e-mail must
  stay true. A group cannot be closed while payments are pending. Reopen it to continue.
- **Who may do what.** Any member can add expenses (also on behalf of someone else), invite, close and reopen. Only whoever
  added an expense or paid it can edit or delete it. A member can leave when their balance is zero and nothing is pending;
  the creator can remove such members and delete a closed (or still empty) group. If the creator leaves, the longest-standing
  member becomes creator, so a group is never left without an administrator. Names of people who left stay on old expenses.
- **Concurrency.** Creating, editing and deleting an expense, payments, joining, leaving and closing take a row lock on the
  group, so a closing group cannot race a new expense or a join. Independent expenses never conflict.
- **Reminders.** A member who has been continuously in debt longer than the group's term gets an e-mail with the amount and
  recipients (from the minimal plan), at most once per 7 days, even if a debt is paid and returns the next day. Closed time
  does not count towards the term (reopening restarts the clock). Each group is processed under its row lock; a background
  loop in the API process runs every 60 s (`REMINDER_INTERVAL_SECONDS`).
- **Live updates** use Server-Sent Events (`/api/stream`): after each change the server tells every member's open clients,
  bursts are batched for 100 ms, and a screen about one group refetches only for that group (and after a reconnect). The hub is
  in-process, so the API runs one worker. To scale out, replace `events.publish` with Postgres LISTEN/NOTIFY.
- **Auth.** E-mail + password (scrypt), opaque random bearer tokens (SHA-256 hashed in the DB), 30-day expiry, logout revokes.
  Eight wrong passwords in five minutes for one e-mail from one address give 429; behind the bundled nginx the real client
  address comes from `X-Forwarded-For` (`TRUST_PROXY=1`, set in compose), otherwise one stranger could lock anyone out. Only the live
  stream accepts the token as `?access_token=` (`EventSource` cannot send headers) and it uses its own short DB session.
- **Invites.** The group link is shared and can be rotated; an e-mail invite carries its own personal link that survives a rotation.
- **Receipts.** PNG/JPEG/WebP/PDF up to 5 MB; the type is detected from the file's own bytes, files are served to members only,
  as attachments with `nosniff`; replacing or deleting removes the old file.
- **Errors.** Every API error has a stable code; the web client keeps one Russian text per code, and a test fails if a code has no
  translation. Validation errors are turned into readable Russian, never raw JSON.
- **Input bounds.** At most 200 participants per split, weights 1..1 000 000, ids in the 32-bit range, duplicates are a 422.

## Independent review

Three read-only reviewers (business logic, security/concurrency, frontend) went through the repo; every finding was confirmed
before fixing and each fix has a test that fails without it. Later, a browser test found one more real defect (a creator who
left stranded the group). Details and the order of work are in DEVLOG.

## Honest status

Works and is tested: everything above.

Known gaps, not hidden:
- **E-mail is a stub and addresses are not verified.** Whoever registers an address first can read its "mailbox" (invites,
  closing summaries). Fine for a demo; with real e-mail the mailbox endpoint must be off (`DEV_MAILBOX=0`) and addresses verified.
  Registration also reveals whether an e-mail exists (409). There is no password reset.
- **The token lives in `sessionStorage`**, readable by any script on the page. That is a deliberate trade-off: it makes every tab
  its own session (two people side by side in one browser). An httpOnly cookie would be safer and would remove that.
- Live updates need a single API worker (in-process hub); the login throttle is in memory, per process.
- The browser scenarios cover the main paths; editing, reminders and receipts in the browser are covered at API/component level.
  Frontend line coverage from unit tests is ~37 % (pages are covered by the browser scenarios, not by unit tests).
- "Who owes you" across all groups is derived from each group's minimal plan, so the counterparties can change after an edit;
  the totals are exact, the attribution to a person is a view of the plan.
- Any member can close, reopen or change a group's settings (the case does not say who may).
- The UI is Russian only. Payments are not tied to a payment method; there is no currency conversion (a group has one currency).
- Not run in CI: `scripts/perf.py` (numbers above are from one laptop).
- A crash of the **database** server in the middle of a write is covered only by PostgreSQL's own guarantees (a dropped connection is
  tested, a crashed database is not). Idempotency keys cover create-expense and create-payment; other actions (confirm, close,
  leave) are naturally safe to repeat or answer with a clear conflict.
- Compose passwords are development defaults; there is no TLS termination (put a proxy in front for real use).

## Next steps

Verified e-mail addresses and a real SMTP transport behind the existing `send_email` seam; password reset; an httpOnly-cookie
session option; LISTEN/NOTIFY hub and multiple workers; a load test; more browser paths (edit/delete, reminders).

## Made with

Written with Claude Code (Claude Sonnet 5.5). Nothing is copied from a template or generator: Vite's scaffold was not used
(files are hand-written), the Alembic migrations were produced with `alembic revision` (the first with `--autogenerate`), and the
UI colors come from the Notion style on styles.refero.design. See `docs/PROMPTS.md` and `DEVLOG.md`.
