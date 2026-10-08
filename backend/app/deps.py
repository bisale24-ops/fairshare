from datetime import timedelta

from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from . import config
from .errors import ApiError
from .db import SessionLocal, get_db
from .models import AuthToken, Group, Membership, User, now_utc
from .security import token_hash

STREAM_PATH = "/api/stream"


def _raw_token(request: Request, authorization: str | None, access_token: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    # EventSource cannot set headers, so ONLY the live stream may take the token from the query string.
    # Every other route ignores it, which keeps it out of reach of ordinary links, logs and referrers.
    if access_token and request.url.path == STREAM_PATH:
        return access_token
    raise ApiError(401, "not_authenticated", "Not authenticated")


def _user_for_token(db: Session, raw: str) -> User:
    row = db.get(AuthToken, token_hash(raw))
    if not row or now_utc() - row.created_at > timedelta(days=config.TOKEN_TTL_DAYS):
        raise ApiError(401, "session_invalid", "Invalid or expired token")
    user = db.get(User, row.user_id)
    if not user:
        raise ApiError(401, "session_invalid", "Invalid token")
    return user


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    return _user_for_token(db, _raw_token(request, authorization, access_token))


def stream_user(
    request: Request,
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
) -> User:
    """Like current_user, but takes its own short-lived DB session.

    A stream stays open for hours; a session injected with Depends(get_db) would stay checked out of the
    connection pool for that whole time, and a few open tabs would exhaust the pool.
    """
    with SessionLocal() as db:
        return _user_for_token(db, _raw_token(request, authorization, access_token))


def member_group(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Group:
    group = db.get(Group, group_id)
    if not group or not db.get(Membership, (group_id, user.id)):
        raise ApiError(404, "group_not_found", "Group not found")
    return group
