from __future__ import annotations

from fastapi import Header
from sqlalchemy.orm import Session

from .errors import ApiError
from .models import IdempotencyKey


def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str | None:
    if idempotency_key is None:
        return None
    if not 8 <= len(idempotency_key) <= 80:
        raise ApiError(422, "idempotency_key_invalid", "Idempotency-Key must be 8 to 80 characters")
    return idempotency_key


def already_done(db: Session, user_id: int, key: str | None, kind: str) -> int | None:
    """The id this key produced before, or None. Call it AFTER taking the group lock so two identical requests cannot both pass."""
    if key is None:
        return None
    row = db.get(IdempotencyKey, (user_id, key))
    if row is None:
        return None
    if row.kind != kind:
        raise ApiError(409, "idempotency_key_reused", "This Idempotency-Key was already used for something else")
    return row.entity_id


def remember(db: Session, user_id: int, key: str | None, kind: str, entity_id: int) -> None:
    if key is not None:
        db.add(IdempotencyKey(user_id=user_id, key=key, kind=kind, entity_id=entity_id))
