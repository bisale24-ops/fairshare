from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, member_group
from ..ledger import compute_balances, fmt, log_activity, member_ids, notify, push_live, refresh_debt_state, user_names
from ..models import Group, Settlement, User, now_utc
from ..schemas import SettlementIn

router = APIRouter(prefix="/api", tags=["settlements"])


def settlement_view(s: Settlement, names: dict[int, str]) -> dict:
    return {
        "id": s.id,
        "group_id": s.group_id,
        "from_user": s.from_user,
        "from_name": names.get(s.from_user),
        "to_user": s.to_user,
        "to_name": names.get(s.to_user),
        "amount_minor": s.amount,
        "status": s.status,
        "created_at": s.created_at,
        "resolved_at": s.resolved_at,
    }


def _lock_group(db: Session, group_id: int) -> Group:
    return db.execute(select(Group).where(Group.id == group_id).with_for_update()).scalar_one()


def _frozen(group: Group) -> None:
    if group.closed:
        raise HTTPException(409, "The group is closed: reopen it to record or confirm payments")


def _check_limits(db: Session, group: Group, from_user: int, to_user: int, amount: int, pending_excluded_id: int | None = None) -> None:
    """A payment may not exceed what the debtor owes, nor what the receiver is owed.

    Payments still waiting for confirmation between the same two people count against the limit,
    so several pending payments cannot add up to more than the debt.
    """
    balances = compute_balances(db, group.id)
    owes = -balances.get(from_user, 0)
    owed = balances.get(to_user, 0)
    if owes <= 0:
        raise HTTPException(409, "You do not owe anything in this group")
    if owed <= 0:
        raise HTTPException(409, "The receiver is not owed anything in this group")
    pending = db.scalar(
        select(func.coalesce(func.sum(Settlement.amount), 0)).where(
            Settlement.group_id == group.id,
            Settlement.from_user == from_user,
            Settlement.to_user == to_user,
            Settlement.status == "pending",
            Settlement.id != (pending_excluded_id or 0),
        )
    )
    limit = min(owes, owed) - int(pending or 0)
    if limit <= 0:
        raise HTTPException(409, "Payments already waiting for confirmation cover the whole debt")
    if amount > limit:
        raise HTTPException(409, f"Amount is more than can be settled between you now (max {fmt(limit, group.currency)})")


@router.post("/groups/{group_id}/settlements", status_code=201)
def create_settlement(
    data: SettlementIn, group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    group = _lock_group(db, group.id)
    _frozen(group)
    if data.to_user == user.id or data.to_user not in set(member_ids(db, group.id)):
        raise HTTPException(422, "The receiver must be another member of the group")
    _check_limits(db, group, user.id, data.to_user, data.amount_minor)
    s = Settlement(group_id=group.id, from_user=user.id, to_user=data.to_user, amount=data.amount_minor)
    db.add(s)
    db.flush()
    log_activity(db, group.id, user.id, "settlement_proposed", {"settlement_id": s.id, "to_user": s.to_user, "amount_minor": s.amount})
    notify(db, s.to_user, group.id, "settlement_proposed", f"{user.name} says they paid you {fmt(s.amount, group.currency)} in {group.name}: please confirm")
    db.commit()
    push_live(db, group.id, "settlement_proposed")
    return settlement_view(s, user_names(db, [s.from_user, s.to_user]))


@router.get("/groups/{group_id}/settlements")
def list_settlements(group: Group = Depends(member_group), db: Session = Depends(get_db)):
    rows = db.scalars(select(Settlement).where(Settlement.group_id == group.id).order_by(Settlement.id.desc())).all()
    names = user_names(db, member_ids(db, group.id))
    return [settlement_view(s, names) for s in rows]


def _resolve(settlement_id: int, user: User, db: Session, status: str) -> dict:
    s = db.get(Settlement, settlement_id)
    if not s:
        raise HTTPException(404, "Settlement not found")
    group = _lock_group(db, s.group_id)
    db.refresh(s)
    if user.id not in member_ids(db, group.id):
        raise HTTPException(404, "Settlement not found")
    _frozen(group)
    if s.to_user != user.id:
        raise HTTPException(403, "Only the receiver can confirm or reject a payment")
    if s.status != "pending":
        raise HTTPException(409, f"Settlement is already {s.status}")
    if status == "confirmed":
        _check_limits(db, group, s.from_user, s.to_user, s.amount, pending_excluded_id=s.id)
    s.status = status
    s.resolved_at = now_utc()
    kind = "settlement_confirmed" if status == "confirmed" else "settlement_rejected"
    log_activity(db, group.id, user.id, kind, {"settlement_id": s.id, "from_user": s.from_user, "amount_minor": s.amount})
    verb = "confirmed" if status == "confirmed" else "rejected"
    notify(db, s.from_user, group.id, kind, f"{user.name} {verb} your payment of {fmt(s.amount, group.currency)} in {group.name}")
    refresh_debt_state(db, group)
    db.commit()
    push_live(db, group.id, kind)
    return settlement_view(s, user_names(db, [s.from_user, s.to_user]))


@router.post("/settlements/{settlement_id}/confirm")
def confirm(settlement_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _resolve(settlement_id, user, db, "confirmed")


@router.post("/settlements/{settlement_id}/reject")
def reject(settlement_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _resolve(settlement_id, user, db, "rejected")
