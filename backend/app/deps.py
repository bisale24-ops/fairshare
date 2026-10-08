from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuthToken, Group, Membership, User
from .security import token_hash


def current_user(
    authorization: str | None = Header(default=None),
    access_token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif access_token:
        raw = access_token  # EventSource cannot set headers, so the stream accepts ?token=
    if not raw:
        raise HTTPException(401, "Not authenticated")
    row = db.get(AuthToken, token_hash(raw))
    if not row:
        raise HTTPException(401, "Invalid token")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Invalid token")
    return user


def member_group(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Group:
    group = db.get(Group, group_id)
    if not group or not db.get(Membership, (group_id, user.id)):
        raise HTTPException(404, "Group not found")
    return group
