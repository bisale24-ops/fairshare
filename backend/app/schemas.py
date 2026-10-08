from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=200)

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.lower()


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(min_length=3, max_length=3, pattern="^[A-Za-z]{3}$")
    remind_after_days: int = Field(default=7, ge=1, le=365)

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    remind_after_days: int | None = Field(default=None, ge=1, le=365)


class InviteIn(BaseModel):
    email: EmailStr


class SplitIn(BaseModel):
    type: Literal["equal", "shares", "exact"]
    participants: list[int] | None = None  # equal
    weights: dict[int, int] | None = None  # shares
    amounts: dict[int, int] | None = None  # exact, minor units


class ExpenseIn(BaseModel):
    payer_id: int
    amount_minor: int = Field(gt=0, le=10**12)
    title: str = Field(default="", max_length=200)
    category: str = Field(default="other", max_length=50)
    spent_on: date
    comment: str = Field(default="", max_length=2000)
    split: SplitIn


class SettlementIn(BaseModel):
    to_user: int
    amount_minor: int = Field(gt=0, le=10**12)
