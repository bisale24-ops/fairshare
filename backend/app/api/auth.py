from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import AuthToken, User
from ..schemas import LoginIn, RegisterIn
from ..security import hash_password, new_token, token_hash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
        raise HTTPException(409, "E-mail is already registered")
    return _session(db, user)


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Wrong e-mail or password")
    return _session(db, user)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}
