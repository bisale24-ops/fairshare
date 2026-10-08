from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..errors import ApiError
from ..idempotency import already_done, idempotency_key, remember
from ..db import get_db
from ..deps import current_user, member_group
from ..ledger import fmt, log_activity, member_ids, notify, overpaid, push_live, refresh_debt_state, user_names
from ..models import Expense, ExpenseShare, Group, Membership, User, now_utc
from ..money import SplitError, split_equal, split_exact, split_shares
from ..schemas import ExpenseIn

router = APIRouter(prefix="/api", tags=["expenses"])


def _compute_shares(data: ExpenseIn, members: set[int]) -> tuple[dict[int, int], dict[int, int | None]]:
    s = data.split
    try:
        if s.type == "equal":
            if not s.participants:
                raise SplitError("participants are required for an equal split", "split_need_participants")
            ids = list(dict.fromkeys(s.participants))
            weights: dict[int, int | None] = {uid: None for uid in ids}
            shares = split_equal(data.amount_minor, ids)
        elif s.type == "shares":
            if not s.weights:
                raise SplitError("weights are required for a split by shares", "split_need_weights")
            weights = dict(s.weights)
            shares = split_shares(data.amount_minor, s.weights)
        else:
            if not s.amounts:
                raise SplitError("amounts are required for an exact split", "split_need_amounts")
            weights = {uid: None for uid in s.amounts}
            shares = split_exact(data.amount_minor, s.amounts)
    except SplitError as e:
        raise ApiError(422, e.code, str(e))
    if not set(shares) <= members:
        raise ApiError(422, "participant_not_member", "Every participant must be a member of the group")
    return shares, weights


def expense_view(e: Expense, names: dict[int, str]) -> dict:
    return {
        "id": e.id,
        "version": e.version,
        "group_id": e.group_id,
        "payer_id": e.payer_id,
        "payer_name": names.get(e.payer_id),
        "amount_minor": e.amount,
        "title": e.title,
        "category": e.category,
        "spent_on": e.spent_on,
        "comment": e.comment,
        "split_type": e.split_type,
        "has_receipt": bool(e.receipt_path),
        "receipt_name": e.receipt_name,
        "created_by": e.created_by,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
        "shares": [
            {"user_id": s.user_id, "name": names.get(s.user_id), "amount_minor": s.amount, "weight": s.weight}
            for s in sorted(e.shares, key=lambda s: s.user_id)
        ],
    }


def involved_names(db: Session, group_id: int, expenses: list[Expense]) -> dict[int, str]:
    """Names of current members AND of anyone who took part in these expenses but has since left."""
    ids = set(member_ids(db, group_id))
    for e in expenses:
        ids.add(e.payer_id)
        ids.update(s.user_id for s in e.shares)
    return user_names(db, list(ids))


def _lock_open_group(db: Session, group_id: int) -> Group:
    group = db.execute(select(Group).where(Group.id == group_id).with_for_update()).scalar_one()
    if group.closed:
        raise ApiError(409, "group_closed_expenses", "The group is closed: no new or edited expenses")
    return group


def _notify_participants(db: Session, group: Group, actor: User, user_ids: set[int], kind: str, text: str) -> None:
    for uid in user_ids - {actor.id}:
        notify(db, uid, group.id, kind, text)


@router.post("/groups/{group_id}/expenses", status_code=201)
def create_expense(
    data: ExpenseIn,
    group: Group = Depends(member_group),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    key: str | None = Depends(idempotency_key),
):
    group = _lock_open_group(db, group.id)
    done = already_done(db, user.id, key, "expense")
    if done is not None:  # a retry of a request that already went through: hand back the same expense, create nothing
        original = db.get(Expense, done)
        if original is not None and not original.deleted:
            return expense_view(original, involved_names(db, group.id, [original]))
    members = set(member_ids(db, group.id))
    if data.payer_id not in members:
        raise ApiError(422, "payer_not_member", "The payer must be a member of the group")
    shares, weights = _compute_shares(data, members)
    expense = Expense(
        group_id=group.id,
        payer_id=data.payer_id,
        amount=data.amount_minor,
        title=data.title.strip(),
        category=data.category.strip() or "other",
        spent_on=data.spent_on,
        comment=data.comment,
        split_type=data.split.type,
        created_by=user.id,
        shares=[ExpenseShare(user_id=uid, amount=a, weight=weights.get(uid)) for uid, a in shares.items()],
    )
    db.add(expense)
    db.flush()
    remember(db, user.id, key, "expense", expense.id)
    label = expense.title or expense.category
    log_activity(
        db, group.id, user.id, "expense_added",
        {"expense_id": expense.id, "title": label, "amount_minor": expense.amount, "payer_id": expense.payer_id},
    )
    _notify_participants(
        db, group, user, set(shares) | {expense.payer_id}, "expense_added",
        f"{user.name} added \"{label}\" ({fmt(expense.amount, group.currency)}) in {group.name}",
    )
    refresh_debt_state(db, group)
    db.commit()
    push_live(db, group.id, "expense_added")
    return expense_view(expense, involved_names(db, group.id, [expense]))


@router.get("/groups/{group_id}/expenses")
def list_expenses(
    group: Group = Depends(member_group),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows = db.scalars(
        select(Expense)
        .where(Expense.group_id == group.id, Expense.deleted.is_(False))
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = involved_names(db, group.id, list(rows))
    return [expense_view(e, names) for e in rows]


def _may_change(user: User, expense: Expense) -> None:
    """Only whoever recorded the expense or paid it may edit or delete it; other members can still read it."""
    if user.id not in (expense.created_by, expense.payer_id):
        raise ApiError(403, "not_expense_owner", "Only the person who added the expense or paid for it can change it")


def _get_expense(db: Session, group: Group, expense_id: int) -> Expense:
    e = db.get(Expense, expense_id)
    if not e or e.group_id != group.id or e.deleted:
        raise ApiError(404, "expense_not_found", "Expense not found")
    return e


@router.put("/groups/{group_id}/expenses/{expense_id}")
def edit_expense(
    expense_id: int,
    data: ExpenseIn,
    group: Group = Depends(member_group),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    group = _lock_open_group(db, group.id)
    expense = _get_expense(db, group, expense_id)
    _may_change(user, expense)
    if data.version is not None and data.version != expense.version:
        raise ApiError(409, "expense_conflict", "This expense was changed by someone else in the meantime: reload it and try again")
    members = set(member_ids(db, group.id))
    # a person who took part in THIS expense and has since left may stay in it; nobody new may be added from outside
    allowed = members | {s.user_id for s in expense.shares} | {expense.payer_id}
    if data.payer_id not in allowed:
        raise ApiError(422, "payer_not_member", "The payer must be a member of the group")
    shares, weights = _compute_shares(data, allowed)
    touched = {s.user_id for s in expense.shares} | {expense.payer_id}
    expense.payer_id = data.payer_id
    expense.amount = data.amount_minor
    expense.title = data.title.strip()
    expense.category = data.category.strip() or "other"
    expense.spent_on = data.spent_on
    expense.comment = data.comment
    expense.split_type = data.split.type
    expense.updated_at = now_utc()
    expense.version += 1
    expense.shares.clear()
    db.flush()
    expense.shares.extend(ExpenseShare(user_id=uid, amount=a, weight=weights.get(uid)) for uid, a in shares.items())
    db.flush()
    label = expense.title or expense.category
    log_activity(
        db, group.id, user.id, "expense_edited",
        {"expense_id": expense.id, "title": label, "amount_minor": expense.amount},
    )
    _notify_participants(
        db, group, user, touched | set(shares) | {expense.payer_id}, "expense_edited",
        f"{user.name} edited \"{label}\" in {group.name}: now {fmt(expense.amount, group.currency)}",
    )
    refresh_debt_state(db, group)
    warnings = overpaid(db, group.id)
    if warnings:
        log_activity(db, group.id, user.id, "settlement_overpaid", {"expense_id": expense.id, "people": warnings})
    db.commit()
    push_live(db, group.id, "expense_edited")
    return {**expense_view(expense, involved_names(db, group.id, [expense])), "warnings": warnings}


@router.delete("/groups/{group_id}/expenses/{expense_id}")
def delete_expense(
    expense_id: int, group: Group = Depends(member_group), user: User = Depends(current_user), db: Session = Depends(get_db)
):
    group = _lock_open_group(db, group.id)
    expense = _get_expense(db, group, expense_id)
    _may_change(user, expense)
    expense.deleted = True
    expense.updated_at = now_utc()
    orphan = expense.receipt_path
    expense.receipt_path = None
    expense.receipt_name = None
    label = expense.title or expense.category
    log_activity(db, group.id, user.id, "expense_deleted", {"expense_id": expense.id, "title": label, "amount_minor": expense.amount})
    _notify_participants(
        db, group, user, {s.user_id for s in expense.shares} | {expense.payer_id}, "expense_deleted",
        f"{user.name} deleted \"{label}\" in {group.name}",
    )
    refresh_debt_state(db, group)
    warnings = overpaid(db, group.id)
    if warnings:
        log_activity(db, group.id, user.id, "settlement_overpaid", {"expense_id": expense.id, "people": warnings})
    db.commit()
    if orphan:
        _remove_file(orphan)
    push_live(db, group.id, "expense_deleted")
    return {"ok": True, "warnings": warnings}


def _remove_file(name: str) -> None:
    try:
        os.remove(os.path.join(config.UPLOAD_DIR, os.path.basename(name)))
    except OSError:
        pass


def _sniff_receipt(head: bytes) -> tuple[str, str] | None:
    """Real type from the file's own bytes; the client-declared Content-Type is not trusted."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp", "image/webp"
    if head.startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    return None


RECEIPT_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".pdf": "application/pdf"}


@router.post("/groups/{group_id}/expenses/{expense_id}/receipt")
def upload_receipt(  # plain def on purpose: blocking file/DB work runs in the thread pool, not on the event loop
    expense_id: int,
    file: UploadFile = File(...),
    group: Group = Depends(member_group),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    group = _lock_open_group(db, group.id)
    expense = _get_expense(db, group, expense_id)
    content = file.file.read(config.MAX_RECEIPT_BYTES + 1)
    if len(content) > config.MAX_RECEIPT_BYTES:
        raise ApiError(413, "receipt_too_large", "Receipt is too large")
    sniffed = _sniff_receipt(content[:16])
    if not sniffed:
        raise ApiError(415, "receipt_bad_type", "Receipt must be a real PNG, JPEG, WebP or PDF file")
    ext, _ = sniffed
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(config.UPLOAD_DIR, name)
    with open(path, "wb") as fh:
        fh.write(content)
    old = expense.receipt_path
    expense.receipt_path = name
    expense.receipt_name = os.path.basename(file.filename or "receipt")[:200]
    log_activity(db, group.id, user.id, "receipt_attached", {"expense_id": expense.id, "title": expense.title or expense.category})
    try:
        db.commit()
    except Exception:
        os.remove(path)  # no orphan file if the transaction fails
        raise
    if old:
        _remove_file(old)
    push_live(db, group.id, "receipt_attached")
    return {"ok": True, "receipt_name": expense.receipt_name}


@router.get("/groups/{group_id}/expenses/{expense_id}/receipt")
def download_receipt(expense_id: int, group: Group = Depends(member_group), db: Session = Depends(get_db)):
    expense = _get_expense(db, group, expense_id)
    if not expense.receipt_path:
        raise ApiError(404, "no_receipt", "No receipt")
    path = os.path.join(config.UPLOAD_DIR, os.path.basename(expense.receipt_path))
    if not os.path.exists(path):
        raise ApiError(404, "receipt_file_missing", "Receipt file is missing")
    media = RECEIPT_MEDIA.get(os.path.splitext(path)[1], "application/octet-stream")
    # media type comes from the stored extension (set from the sniffed bytes), never from the user's file name
    return FileResponse(
        path, media_type=media, filename=expense.receipt_name or "receipt", content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff"},
    )
