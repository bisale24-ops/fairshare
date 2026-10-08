from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .ledger import compute_balances, fmt, notify, plan, push_live, refresh_debt_state, user_names
from .mail import send_email
from .models import DebtState, Group, User, now_utc


def _remind_group(db: Session, group: Group, now: datetime) -> int:
    refresh_debt_state(db, group, now)
    db.flush()
    balances = compute_balances(db, group.id)
    transfers = plan(db, group.id)
    names = user_names(db, list(balances))
    sent = 0
    for state in db.scalars(select(DebtState).where(DebtState.group_id == group.id, DebtState.since.is_not(None))):
        if balances.get(state.user_id, 0) >= 0:
            continue  # paid: never remind (refresh_debt_state has also just cleared the clock)
        if now - state.since < timedelta(days=group.remind_after_days):
            continue
        if state.last_reminded_at and now - state.last_reminded_at < timedelta(days=config.REMINDER_MIN_GAP_DAYS):
            continue
        user = db.get(User, state.user_id)
        mine = [t for t in transfers if t.from_user == state.user_id]
        lines = [f"- {fmt(t.amount, group.currency)} to {names.get(t.to_user, '?')}" for t in mine]
        body = (
            f"Hi {user.name},\n\nYou still owe in the group \"{group.name}\" "
            f"(open for {(now - state.since).days} days):\n" + "\n".join(lines) + "\n"
        )
        send_email(db, user.email, f"Reminder: you owe money in {group.name}", body, "reminder", group.id)
        notify(db, user.id, group.id, "reminder", f"You owe {fmt(-balances[user.id], group.currency)} in {group.name}")
        state.last_reminded_at = now
        sent += 1
    return sent


def run_reminders(db: Session, now: datetime | None = None) -> int:
    """Send e-mail reminders to overdue debtors; returns how many were sent.

    A reminder goes out when: the group is open, the member is still in debt, the debt has been continuous for at
    least the group's remind_after_days, and no reminder was sent in the last REMINDER_MIN_GAP_DAYS (a week, even
    across a paid-and-re-incurred debt). Each group is processed under its row lock (skipping groups someone else
    holds), so a payment confirmed at that moment, or a second runner, cannot produce a reminder for someone who just paid.
    """
    now = now or now_utc()
    total = 0
    ids = list(db.scalars(select(Group.id).where(Group.closed.is_(False))))
    for gid in ids:
        group = db.execute(select(Group).where(Group.id == gid, Group.closed.is_(False)).with_for_update(skip_locked=True)).scalar_one_or_none()
        if group is None:
            continue
        sent = _remind_group(db, group, now)
        db.commit()  # releases the group lock
        if sent:
            push_live(db, gid, "reminder")
        total += sent
    return total
