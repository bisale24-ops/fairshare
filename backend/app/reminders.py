from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .ledger import compute_balances, fmt, notify, plan, push_live, refresh_debt_state, user_names
from .mail import send_email
from .models import DebtState, Group, User, now_utc


def run_reminders(db: Session, now: datetime | None = None) -> int:
    """Send e-mail reminders to overdue debtors; returns how many were sent.

    A reminder goes out when: the group is open, the member is *still* in debt, the
    debt has been continuous for at least the group's remind_after_days, and no reminder
    was sent within the last REMINDER_MIN_GAP_DAYS (a week). A debt that was paid is never
    reminded about, because refresh_debt_state() drops it the moment the balance stops
    being negative.
    """
    now = now or now_utc()
    sent = 0
    for group in db.scalars(select(Group).where(Group.closed.is_(False))):
        refresh_debt_state(db, group, now)
        db.flush()
        balances = compute_balances(db, group.id)
        transfers = plan(db, group.id)
        names = user_names(db, list(balances))
        for state in db.scalars(select(DebtState).where(DebtState.group_id == group.id)):
            if balances.get(state.user_id, 0) >= 0:
                continue
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
        push_live(db, group.id, "reminder") if sent else None
    db.commit()
    return sent
