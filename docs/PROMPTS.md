# Prompts and who decided what

**Tool:** Claude Code (CLI) with Claude Sonnet 5.5 as the coding agent. It is the tool I use every day, and it
can run the code, the tests and the browser checks itself, so the claims in this repo come from commands that were run.

## What I (the human) actually told the agent

Verbatim, in Russian, as sent:

1. «проверь почту там ответили по вакансии и предложили тестовые задания на выбор» — the agent read the e-mail
   and the PDF with 14 cases and recommended case 6, because it overlaps with my own SplitBill app and my Tally MCP project.
2. «кейс 6, срок до субботы, эссе делаем» — my decision: case 6, due Saturday, essay included.

Standing instructions I keep for every project (global CLAUDE.md): take design references from refero.design,
and build to win rather than to get a minimum through.

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
