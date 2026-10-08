from __future__ import annotations

from collections import defaultdict

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import config, events
from ..db import get_db
from ..deps import current_user, member_group
from ..ledger import (
    compute_balances,
    fmt,
    log_activity,
    member_ids,
    notify,
    plan,
    push_live,
    refresh_debt_state,
    user_names,
)
from ..mail import send_email
from ..models import (
    Activity,
    DebtState,
    Expense,
    ExpenseShare,
    Group,
    Invite,
    Membership,
    Settlement,
    User,
    now_utc,
)
from ..schemas import GroupIn, GroupPatch, InviteIn
from ..security import new_token

router = APIRouter(prefix="/api", tags=["groups"])


def _transfers_view(db: Session, group: Group, balances: dict[int, int] | None = None):
    transfers = plan(db, group.id, balances)
    names = user_names(db, [t.from_user for t in transfers] + [t.to_user for t in transfers])
    return [
        {
            "from_user": t.from_user,
            "from_name": names[t.from_user],
            "to_user": t.to_user,
            "to_name": names[t.to_user],
            "amount_minor": t.amount,
        }
        for t in transfers
    ]


def group_view(db: Session, group: Group, me: User) -> dict:
    ids = member_ids(db, group.id)
    names = user_names(db, ids)
    balances = compute_balances(db, group.id)
    return {
        "id": group.id,
        "name": group.name,
        "currency": group.currency,
        "remind_after_days": group.remind_after_days,
        "closed": group.closed,
        "closed_at": group.closed_at,
        "invite_token": group.invite_token,
        "created_by": group.created_by,
        "members": [
            {"id": uid, "name": names[uid], "balance_minor": balances.get(uid, 0)} for uid in ids
        ],
        "my_balance_minor": balances.get(me.id, 0),
        "transfers": _transfers_view(db, group, balances),
    }


@router.post("/groups", status_code=201)
def create_group(data: GroupIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    group = Group(
        name=data.name.strip(),
        currency=data.currency,
        remind_after_days=data.remind_after_days,
        invite_token=new_token(),
        created_by=user.id,
    )
    db.add(group)
    db.flush()
    db.add(Membership(group_id=group.id, user_id=user.id))
    log_activity(db, group.id, user.id, "group_created", {"name": group.name})
    db.commit()
    return group_view(db, group, user)


@router.get("/groups")
def list_groups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    groups = db.scalars(
        select(Group).join(Membership, Membership.group_id == Group.id).where(Membership.user_id == user.id).order_by(Group.id.desc())
    ).all()
    out = []
    for g in groups:
        balances = compute_balances(db, g.id)
        out.append(
            {
                "id": g.id,
                "name": g.name,
                "currency": g.currency,
                "closed": g.closed,
                "members": len(balances),
                "my_balance_minor": balances.get(user.id, 0),
            }
        )
    return out


@router.get("/groups/{group_id}")
def get_group(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    return group_view(db, group, user)


@router.patch("/groups/{group_id}")
def patch_group(
    data: GroupPatch, group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if data.name is not None:
        group.name = data.name.strip()
    if data.remind_after_days is not None:
        group.remind_after_days = data.remind_after_days
    log_activity(db, group.id, user.id, "group_updated", {"name": group.name, "remind_after_days": group.remind_after_days})
    db.commit()
    push_live(db, group.id, "group_updated")
    return group_view(db, group, user)


@router.post("/groups/{group_id}/invites", status_code=201)
def invite_by_email(
    data: InviteIn, group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    group = db.execute(select(Group).where(Group.id == group.id).with_for_update()).scalar_one()
    if group.closed:
        raise HTTPException(409, "The group is closed")
    email = data.email.lower()
    invite = db.scalar(select(Invite).where(Invite.group_id == group.id, Invite.email == email))
    if not invite:
        invite = Invite(group_id=group.id, email=email, token=new_token())
        db.add(invite)
        db.flush()
    link = f"{config.BASE_URL}/#/join/{invite.token}"
    send_email(
        db,
        email,
        f"{user.name} invited you to {group.name}",
        f"{user.name} invited you to the expense group \"{group.name}\" ({group.currency}).\nJoin: {link}\n",
        "invite",
        group.id,
    )
    log_activity(db, group.id, user.id, "invited", {"email": email})
    db.commit()
    return {"email": email, "link": link}


def _group_by_token(db: Session, token: str, lock: bool = False) -> tuple[Group, Invite | None]:
    """A join token is either the group's shared link or one person's own e-mail invite."""
    invite = db.scalar(select(Invite).where(Invite.token == token))
    q = select(Group).where(Group.id == invite.group_id) if invite else select(Group).where(Group.invite_token == token)
    group = db.scalar(q.with_for_update() if lock else q)
    if not group:
        raise HTTPException(404, "Invite link is invalid")
    return group, invite


@router.get("/join/{token}")
def join_info(token: str, db: Session = Depends(get_db)):
    group, _ = _group_by_token(db, token)
    return {"group_id": group.id, "name": group.name, "currency": group.currency, "closed": group.closed}


@router.post("/join/{token}")
def join(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    group, invite = _group_by_token(db, token, lock=True)  # same lock as close/expense: no join slips past a close
    if not db.get(Membership, (group.id, user.id)):
        if group.closed:
            raise HTTPException(409, "The group is closed")
        db.add(Membership(group_id=group.id, user_id=user.id))
        if invite and not invite.accepted_at:
            invite.accepted_at = now_utc()
        log_activity(db, group.id, user.id, "joined", {"name": user.name})
        db.commit()
        push_live(db, group.id, "joined")
    return group_view(db, group, user)


@router.post("/groups/{group_id}/invite-link/rotate")
def rotate_invite_link(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Old shared link stops working; personal e-mail invites keep working."""
    group.invite_token = new_token()
    log_activity(db, group.id, user.id, "invite_link_rotated", {})
    db.commit()
    return group_view(db, group, user)


@router.get("/groups/{group_id}/activity")
def activity(group: Group = Depends(member_group), db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=500)):
    rows = db.scalars(
        select(Activity).where(Activity.group_id == group.id).order_by(Activity.id.desc()).limit(limit)
    ).all()
    names = user_names(db, [r.actor_id for r in rows if r.actor_id])
    return [
        {"id": r.id, "kind": r.kind, "actor": names.get(r.actor_id), "actor_id": r.actor_id, "payload": r.payload, "created_at": r.created_at}
        for r in rows
    ]


def _report(db: Session, group: Group) -> dict:
    ids = member_ids(db, group.id)
    names = user_names(db, ids)
    balances = compute_balances(db, group.id)
    expenses = db.scalars(select(Expense).where(Expense.group_id == group.id, Expense.deleted.is_(False))).all()
    paid: dict[int, int] = defaultdict(int)
    owed: dict[int, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    for e in expenses:
        paid[e.payer_id] += e.amount
        by_category[e.category] += e.amount
        for s in e.shares:
            owed[s.user_id] += s.amount
    sent: dict[int, int] = defaultdict(int)
    received: dict[int, int] = defaultdict(int)
    for frm, to, amount in db.execute(
        select(Settlement.from_user, Settlement.to_user, Settlement.amount).where(Settlement.group_id == group.id, Settlement.status == "confirmed")
    ):
        sent[frm] += amount
        received[to] += amount
    settled = db.scalar(
        select(func.coalesce(func.sum(Settlement.amount), 0)).where(Settlement.group_id == group.id, Settlement.status == "confirmed")
    )
    return {
        "group": {"id": group.id, "name": group.name, "currency": group.currency, "closed": group.closed},
        "expense_count": len(expenses),
        "total_spent_minor": sum(e.amount for e in expenses),
        "settled_minor": int(settled or 0),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        "members": [
            {
                "id": uid,
                "name": names[uid],
                "paid_minor": paid[uid],
                "share_minor": owed[uid],
                "settled_out_minor": sent[uid],
                "settled_in_minor": received[uid],
                "balance_minor": balances.get(uid, 0),
            }
            for uid in ids
        ],
        "transfers": _transfers_view(db, group, balances),
    }


@router.get("/groups/{group_id}/report")
def report(group: Group = Depends(member_group), db: Session = Depends(get_db)):
    return _report(db, group)


@router.post("/groups/{group_id}/close")
def close_group(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(select(Group).where(Group.id == group.id).with_for_update())  # serialise with expense creation
    db.refresh(group)
    if group.closed:
        raise HTTPException(409, "The group is already closed")
    if db.scalar(select(func.count()).select_from(Settlement).where(Settlement.group_id == group.id, Settlement.status == "pending")):
        raise HTTPException(409, "Confirm or reject the pending payments first: the final summary must not change after it is sent")
    group.closed = True
    group.closed_at = now_utc()
    summary = _report(db, group)
    lines = [
        f"- {t['from_name']} pays {t['to_name']} {fmt(t['amount_minor'], group.currency)}" for t in summary["transfers"]
    ] or ["- Everyone is settled up."]
    for m in summary["members"]:
        u = db.get(User, m["id"])
        body = (
            f"The group \"{group.name}\" was closed by {user.name}.\n"
            f"Total spent: {fmt(summary['total_spent_minor'], group.currency)} in {summary['expense_count']} expenses.\n"
            f"Who pays whom:\n" + "\n".join(lines) + "\n"
        )
        send_email(db, u.email, f"{group.name} is closed: final summary", body, "close_summary", group.id)
        notify(db, u.id, group.id, "group_closed", f"{group.name} was closed")
    log_activity(db, group.id, user.id, "group_closed", {"transfers": len(summary["transfers"])})
    db.commit()
    push_live(db, group.id, "group_closed")
    return summary


@router.post("/groups/{group_id}/reopen")
def reopen_group(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(select(Group).where(Group.id == group.id).with_for_update())
    db.refresh(group)
    if not group.closed:
        raise HTTPException(409, "The group is not closed")
    group.closed = False
    group.closed_at = None
    refresh_debt_state(db, group, restart=True)
    log_activity(db, group.id, user.id, "group_reopened", {})
    db.commit()
    push_live(db, group.id, "group_reopened")
    return group_view(db, group, user)


@router.get("/me/balances")
def my_balances(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Everything I owe / am owed across all my groups, per currency (currencies are never mixed)."""
    groups = db.scalars(
        select(Group).join(Membership, Membership.group_id == Group.id).where(Membership.user_id == user.id)
    ).all()
    per_currency: dict[str, dict] = {}
    for g in groups:
        balances = compute_balances(db, g.id)
        bal = balances.get(user.id, 0)
        cur = per_currency.setdefault(g.currency, {"currency": g.currency, "net_minor": 0, "groups": [], "_people": defaultdict(int)})
        cur["net_minor"] += bal
        cur["groups"].append({"group_id": g.id, "name": g.name, "balance_minor": bal, "closed": g.closed})
        for t in plan(db, g.id, balances):
            if t.from_user == user.id:
                cur["_people"][t.to_user] -= t.amount
            elif t.to_user == user.id:
                cur["_people"][t.from_user] += t.amount
    out = []
    for cur in per_currency.values():
        people = cur.pop("_people")
        names = user_names(db, list(people))
        cur["people"] = [
            {"user_id": uid, "name": names[uid], "amount_minor": amt} for uid, amt in sorted(people.items()) if amt != 0
        ]
        out.append(cur)
    return out


def _may_leave(db: Session, group: Group, uid: int) -> None:
    """A member can only go once nothing depends on them: balance zero, no payment waiting for their answer."""
    if compute_balances(db, group.id).get(uid, 0) != 0:
        raise HTTPException(409, "Settle up first: this person's balance in the group is not zero")
    waiting = db.scalar(
        select(func.count()).select_from(Settlement).where(
            Settlement.group_id == group.id, Settlement.status == "pending", (Settlement.from_user == uid) | (Settlement.to_user == uid)
        )
    )
    if waiting:
        raise HTTPException(409, "Confirm or reject the pending payments first")


def _remove_member(db: Session, group: Group, uid: int, actor: User, kind: str) -> None:
    ids = member_ids(db, group.id)
    if uid not in ids:
        raise HTTPException(404, "Not a member")
    if len(ids) == 1:
        raise HTTPException(409, "The last member cannot leave: delete the group instead")
    _may_leave(db, group, uid)
    db.delete(db.get(Membership, (group.id, uid)))
    db.execute(delete(DebtState).where(DebtState.group_id == group.id, DebtState.user_id == uid))
    name = db.get(User, uid).name
    log_activity(db, group.id, actor.id, kind, {"name": name, "user_id": uid})
    notify(db, uid, group.id, kind, f"{'You left' if kind == 'left' else 'You were removed from'} {group.name}")


@router.post("/groups/{group_id}/leave")
def leave_group(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(select(Group).where(Group.id == group.id).with_for_update())
    ids = member_ids(db, group.id)
    _remove_member(db, group, user.id, user, "left")
    db.commit()
    events.publish(ids, {"type": "group_changed", "group_id": group.id, "kind": "left"})
    return {"ok": True}


@router.delete("/groups/{group_id}/members/{user_id}")
def remove_member(user_id: int, group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(select(Group).where(Group.id == group.id).with_for_update())
    if group.created_by != user.id:
        raise HTTPException(403, "Only the person who created the group can remove members")
    if user_id == user.id:
        raise HTTPException(422, "Use 'leave' to leave the group yourself")
    ids = member_ids(db, group.id)
    _remove_member(db, group, user_id, user, "removed")
    db.commit()
    events.publish(ids, {"type": "group_changed", "group_id": group.id, "kind": "removed"})
    return group_view(db, group, user)


@router.delete("/groups/{group_id}")
def delete_group(group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Creator only, and only for a closed group or one with no expenses yet. Everything in it, receipts included, goes."""
    db.execute(select(Group).where(Group.id == group.id).with_for_update())
    if group.created_by != user.id:
        raise HTTPException(403, "Only the person who created the group can delete it")
    has_expenses = db.scalar(select(func.count()).select_from(Expense).where(Expense.group_id == group.id))
    if not group.closed and has_expenses:
        raise HTTPException(409, "Close the group first (or delete it while it has no expenses)")
    files = [r for r in db.scalars(select(Expense.receipt_path).where(Expense.group_id == group.id)) if r]
    ids = member_ids(db, group.id)
    db.delete(group)  # the database cascades to members, expenses, payments, feed, notifications, invites
    db.commit()
    for name in files:
        try:
            os.remove(os.path.join(config.UPLOAD_DIR, os.path.basename(name)))
        except OSError:
            pass
    events.publish(ids, {"type": "group_changed", "group_id": group.id, "kind": "deleted"})
    return {"ok": True}
