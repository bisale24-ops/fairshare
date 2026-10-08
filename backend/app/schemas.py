from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from .currency import CURRENCIES
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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
    def known(cls, v: str) -> str:
        v = v.upper()
        if v not in CURRENCIES:
            raise ValueError(f"unknown currency code {v}")
        return v


class GroupPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    remind_after_days: int | None = Field(default=None, ge=1, le=365)


class InviteIn(BaseModel):
    email: EmailStr


MAX_PARTICIPANTS = 200
MAX_USER_ID = 2**31 - 1


class SplitIn(BaseModel):
    type: Literal["equal", "shares", "exact"]
    participants: list[Annotated[int, Field(ge=1, le=MAX_USER_ID)]] | None = Field(default=None, max_length=MAX_PARTICIPANTS)  # equal
    weights: dict[Annotated[int, Field(ge=1, le=MAX_USER_ID)], Annotated[int, Field(ge=1, le=1_000_000)]] | None = None  # shares
    amounts: dict[Annotated[int, Field(ge=1, le=MAX_USER_ID)], Annotated[int, Field(ge=0, le=10**12)]] | None = None  # exact, minor units

    @model_validator(mode="after")
    def _bounded_and_unique(self):
        if self.participants is not None and len(set(self.participants)) != len(self.participants):
            raise ValueError("participants must not repeat")
        for name in ("weights", "amounts"):
            value = getattr(self, name)
            if value is not None and len(value) > MAX_PARTICIPANTS:
                raise ValueError(f"{name} has too many entries")
        return self


class ExpenseIn(BaseModel):
    payer_id: int = Field(ge=1, le=MAX_USER_ID)
    amount_minor: int = Field(gt=0, le=10**12)
    title: str = Field(default="", max_length=200)
    category: str = Field(default="other", max_length=50)
    spent_on: date
    comment: str = Field(default="", max_length=2000)
    split: SplitIn
    version: int | None = Field(default=None, ge=1)  # on edit: the version the client last saw


class SettlementIn(BaseModel):
    """Record a payment. Give `to_user` if YOU paid them, or `from_user` if THEY paid you; the other side confirms."""

    to_user: int | None = Field(default=None, ge=1, le=MAX_USER_ID)
    from_user: int | None = Field(default=None, ge=1, le=MAX_USER_ID)
    amount_minor: int = Field(gt=0, le=10**12)

    @model_validator(mode="after")
    def _one_direction(self):
        if (self.to_user is None) == (self.from_user is None):
            raise ValueError("give exactly one of to_user (I paid) or from_user (I was paid)")
        return self
