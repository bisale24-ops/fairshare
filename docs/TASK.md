# Task (Mad Devs, case 6 — shared expenses)

Source: "Задания Agentic Developer (2).pdf", case 6. Received 2026-10-08, due 2026-10-10 (Sat).

Must have: groups with members (invite by link or e-mail), group currency; expenses (payer, amount,
split equally / by shares / exact amounts, category, date, comment, receipt file); balances per group
and across all groups; settlements (full/partial) confirmed by the receiver; group activity feed;
reminders to debtors; closing a group with a final report (re-openable).

Behaviour: balances update live for all members after each expense; minimal set of transfers;
notification on expense involving you / edited; no lost cents (shares always sum to the expense,
leftover-cent rule is fixed and documented); editing/deleting an old expense recomputes everything
including settlements; a settlement counts only after confirmation (pending is visible to both);
reminder to a debtor overdue beyond the group's term, at most once a week, never if paid; two
concurrent expenses both counted and all balances sum to zero; closed group takes no new expenses and
sends everyone a summary e-mail.

General: client/server, backend Python/Go/Node, frontend Vue or React, relational DB (PostgreSQL),
AI agents expected, prompts/decision log delivered, work visible over time, how to deploy, honest status,
must prove it works, external services may be stubbed, works with two clients open at once.
