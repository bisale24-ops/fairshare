# Prompts and who decided what

**Tool:** Claude Code (CLI) with Claude Sonnet 5.5 as the coding agent. It is the tool I use every day, and it
can run the code, the tests and the browser checks itself, so the claims in this repo come from commands that were run.

## Tasks I set (summary, not a transcript)

Written in business wording; this describes what I asked for and what came back, it is not a copy of the chat. The full list with results
is in `docs/SESSION-LOG.md`, section 1. In short:

1. Check the mail: the employer sent test tasks to choose from. The agent read them and recommended case 6 (it overlaps with my own
   SplitBill and Tally MCP projects).
2. I chose case 6, delivery by Saturday 10 October, with the optional essay.
3. Finish everything left unfinished; then: improve the product, run an independent review and fix what it finds, fix e2e flakiness,
   list the remaining problems and fix them, verify and fix behaviour when the API process crashes, publish the repository.

Standing instructions I keep for every project (global CLAUDE.md): take design references from refero.design, and build to win rather
than to get a minimum through.

## What the agent decided on its own (and I have not reviewed line by line yet)

These are the agent's design choices; they are explained in README.md and DEVLOG.md:

- integer minor units everywhere, a single documented leftover-cent rule;
- balances derived from rows on every read, so edits and deletes cannot leave stale totals;
- exact minimum-transfers solver (bitmask DP up to 14 people, greedy beyond);
- a payment counts only after the receiver confirms; limits on the amount;
- Server-Sent Events for live updates; Alembic migration; tests that run on real Postgres through the migration;
- the Notion style from styles.refero.design for the UI;
- hand-made mutation checks of the tests (DEVLOG, 2026-10-09 01:00).

## Verification the agent ran in the browser

Two browser tabs as two people. It found and fixed two defects: a shared `localStorage` token made both tabs
the same user (now `sessionStorage`), and raw JSON validation errors were shown to users (now readable text).

## Why there is no raw session export

The same agent session also holds unrelated private material (my job search, mail). It is not published.
The decisions, with timestamps, are in DEVLOG.md, and git history shows the work arriving feature by feature.
