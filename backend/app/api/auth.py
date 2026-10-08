import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config
from ..errors import ApiError
from ..db import get_db
from ..deps import current_user
from ..models import AuthToken, User
from ..schemas import LoginIn, RegisterIn
from ..security import hash_password, new_token, token_hash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Same cost for unknown and known e-mails, so response time does not reveal which accounts exist.
_DUMMY_HASH = hash_password("not-a-real-password")
_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "?"


def _throttle_key(request: Request, email: str) -> str:
    return f"{client_ip(request)}|{email}"


def _check_throttle(key: str) -> None:
    now = time.monotonic()
    with _lock:
        q = _failures[key]
        while q and now - q[0] > config.LOGIN_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= config.LOGIN_MAX_FAILURES:
            raise ApiError(429, "too_many_attempts", "Too many failed attempts. Try again in a few minutes.")


def _record_failure(key: str) -> None:
    with _lock:
        _failures[key].append(time.monotonic())


def _session(db: Session, user: User) -> dict:
    token = new_token()
    db.add(AuthToken(token_hash=token_hash(token), user_id=user.id))
    db.commit()
    return {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    user = User(email=data.email, name=data.name.strip(), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken", "E-mail is already registered")
    return _session(db, user)


@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = _throttle_key(request, data.email)
    _check_throttle(key)
    user = db.scalar(select(User).where(User.email == data.email))
    ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        _record_failure(key)
        raise ApiError(401, "bad_credentials", "Wrong e-mail or password")
    return _session(db, user)


@router.post("/logout")
def logout(authorization: str = Header(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(AuthToken, token_hash(authorization[7:].strip()))
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}
