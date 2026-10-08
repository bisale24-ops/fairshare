"""Balances, activity feed, notifications and debt tracking for a group."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import events
from .models import (
    Activity,
    DebtState,
    Expense,
    ExpenseShare,
    Group,
    Membership,
    Notification,
    Settlement,
    User,
    now_utc,
)
from .money import Transfer, minimal_transfers


def member_ids(db: Session, group_id: int) -> list[int]:
    return list(db.scalars(select(Membership.user_id).where(Membership.group_id == group_id).order_by(Membership.user_id)))


def compute_balances(db: Session, group_id: int) -> dict[int, int]:
    """Net balance per member in minor units: positive = is owed, negative = owes.

    Derived from the rows every time (no cached totals), so an edit or a delete of an
    old expense can never leave the numbers stale. The result always sums to zero:
    each expense adds +amount to the payer and subtracts shares that sum to amount.
    """
    balances = {uid: 0 for uid in member_ids(db, group_id)}
    paid = db.execute(
        select(Expense.payer_id, Expense.amount).where(Expense.group_id == group_id, Expense.deleted.is_(False))
    )
    for payer, amount in paid:
        balances[payer] = balances.get(payer, 0) + amount
    owed = db.execute(
        select(ExpenseShare.user_id, ExpenseShare.amount)
        .join(Expense, Expense.id == ExpenseShare.expense_id)
        .where(Expense.group_id == group_id, Expense.deleted.is_(False))
    )
    for uid, amount in owed:
        balances[uid] = balances.get(uid, 0) - amount
    settled = db.execute(
        select(Settlement.from_user, Settlement.to_user, Settlement.amount).where(
            Settlement.group_id == group_id, Settlement.status == "confirmed"
        )
    )
    for frm, to, amount in settled:
        balances[frm] = balances.get(frm, 0) + amount
        balances[to] = balances.get(to, 0) - amount
    return balances


def plan(db: Session, group_id: int) -> list[Transfer]:
    return minimal_transfers(compute_balances(db, group_id))


def log_activity(db: Session, group_id: int, actor_id: int | None, kind: str, payload: dict) -> None:
    db.add(Activity(group_id=group_id, actor_id=actor_id, kind=kind, payload=payload))


def notify(db: Session, user_id: int, group_id: int | None, kind: str, text: str) -> None:
    db.add(Notification(user_id=user_id, group_id=group_id, kind=kind, text=text))


def push_live(db: Session, group_id: int, kind: str) -> None:
    """Tell every member's open clients that something changed (they refetch)."""
    events.publish(member_ids(db, group_id), {"type": "group_changed", "group_id": group_id, "kind": kind})


def refresh_debt_state(db: Session, group: Group, now: datetime | None = None, restart: bool = False) -> None:
    """Keep 'in debt since' in sync: set when a balance turns negative, cleared (row kept) when it stops.

    restart=True (used on reopen) moves every current debtor's clock to now: while a group is closed nobody can act on
    a debt, so the closed time must not count towards the reminder term.
    """
    now = now or now_utc()
    balances = compute_balances(db, group.id)
    states = {s.user_id: s for s in db.scalars(select(DebtState).where(DebtState.group_id == group.id))}
    for uid, bal in balances.items():
        state = states.get(uid)
        if bal < 0:
            if state is None:
                db.add(DebtState(group_id=group.id, user_id=uid, since=now))
            elif state.since is None or restart:
                state.since = now
        elif state is not None:
            state.since = None
    for uid, state in states.items():
        if uid not in balances:
            db.delete(state)


def user_names(db: Session, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))}


def fmt(amount: int, currency: str) -> str:
    sign = "-" if amount < 0 else ""
    a = abs(amount)
    return f"{sign}{a // 100}.{a % 100:02d} {currency}"
