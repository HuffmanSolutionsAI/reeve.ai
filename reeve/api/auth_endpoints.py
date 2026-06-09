"""Auth + identity endpoints.

Public:
  POST /api/auth/signup      — create an investor (email + password) + token.
  POST /api/auth/login       — email + password → token.
  POST /api/auth/dev-token   — issue a token for an existing investor id.
                               Dev backdoor; gated by settings.enable_dev_token.

Authenticated:
  GET    /api/me             — current investor (password hash stripped).
  PATCH  /api/me             — update name / entity_name / preferences.
  PATCH  /api/me/buy-box     — update buy-box (any subset of fields).
  PATCH  /api/me/password    — change password (requires the current one).
  DELETE /api/me             — wipe the investor and everything scoped to them.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import AuditKind, EntityType, get_audit
from ..config import settings
from ..models.investor import BuyBox, Investor, InvestorPreferences
from ..repos.investors import (
    delete_investor_cascade,
    get_investor,
    get_investor_by_email,
    update_buy_box_fields,
    update_investor_fields,
    upsert_investor,
)
from .auth import AuthError, issue_token, require_investor_id
from .passwords import hash_password, verify_password


router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def public_dict(investor: Investor) -> dict:
    """Serialize an investor for an API response — without the password hash."""
    data = investor.model_dump(by_alias=True)
    data.pop("password", None)
    return data


def _normalize_email(email: str) -> str:
    norm = email.strip().lower()
    if not _EMAIL_RE.match(norm):
        raise HTTPException(422, "invalid email address")
    return norm


# ---- signup ---------------------------------------------------------------
class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
    name: str = Field(min_length=1, max_length=200)
    entity_name: str | None = None
    buy_box: BuyBox | None = None
    preferences: InvestorPreferences | None = None


@router.post("/auth/signup")
async def signup(body: SignupRequest) -> dict:
    """Create a new investor and immediately issue a token. Public — the
    only path that produces an investor without an existing one."""
    email = _normalize_email(body.email)
    if await get_investor_by_email(email) is not None:
        raise HTTPException(409, "email already registered")

    investor = Investor(
        name=body.name,
        entity_name=body.entity_name,
        email=email,
        password=hash_password(body.password),
        buy_box=body.buy_box or BuyBox(),
        preferences=body.preferences or InvestorPreferences(),
    )
    await upsert_investor(investor)
    get_audit().emit(
        investor_id=investor.id, actor="investor",
        kind=AuditKind.ACT_INTERNAL,
        entity_type=EntityType.INVESTOR, entity_id=investor.id,
        detail={"target": "investor", "action": "signup"},
    )
    return issue_token(investor.id)


# ---- login ----------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
async def login(body: LoginRequest) -> dict:
    """Email + password → token. Returns the same 401 for unknown email and
    wrong password (no account enumeration)."""
    investor = await get_investor_by_email(body.email.strip().lower())
    if investor is None or not verify_password(body.password, investor.password):
        raise AuthError("invalid email or password")
    return issue_token(investor.id)


# ---- dev-token (backdoor) -------------------------------------------------
class DevTokenRequest(BaseModel):
    investor_id: str


@router.post("/auth/dev-token")
async def dev_token(body: DevTokenRequest) -> dict:
    if not settings.enable_dev_token:
        raise HTTPException(404, "not found")
    investor = await get_investor(body.investor_id)
    if investor is None:
        raise HTTPException(404, f"investor {body.investor_id!r} not found")
    return issue_token(body.investor_id)


# ---- /me ------------------------------------------------------------------
@router.get("/me")
async def me(investor_id: str = Depends(require_investor_id)) -> dict:
    investor = await get_investor(investor_id)
    if investor is None:
        raise AuthError("investor in token no longer exists")
    return public_dict(investor)


class InvestorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    entity_name: str | None = None
    preferences: InvestorPreferences | None = None


@router.patch("/me")
async def update_me(
    body: InvestorPatch,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    updates: dict[str, object] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.entity_name is not None:
        updates["entity_name"] = body.entity_name
    if body.preferences is not None:
        updates["preferences"] = body.preferences.model_dump()
    if not updates:
        raise HTTPException(400, "no fields to update")

    investor = await update_investor_fields(investor_id, **updates)
    if investor is None:
        raise HTTPException(404, "investor not found")
    get_audit().emit(
        investor_id=investor_id, actor="investor",
        kind=AuditKind.ACT_INTERNAL,
        entity_type=EntityType.INVESTOR, entity_id=investor_id,
        detail={"target": "investor", "fields": list(updates.keys())},
    )
    return public_dict(investor)


class BuyBoxPatch(BaseModel):
    cap_floor: float | None = Field(default=None, ge=0)
    min_dscr: float | None = Field(default=None, ge=0)
    target_coc: float | None = Field(default=None, ge=0)
    markets: list[str] | None = None
    unit_range: list[int] | None = Field(default=None, min_length=2, max_length=2)
    price_range: list[float] | None = Field(default=None, min_length=2, max_length=2)


@router.patch("/me/buy-box")
async def update_my_buy_box(
    body: BuyBoxPatch,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "no fields to update")
    investor = await update_buy_box_fields(investor_id, **fields)
    if investor is None:
        raise HTTPException(404, "investor not found")
    get_audit().emit(
        investor_id=investor_id, actor="investor",
        kind=AuditKind.ACT_INTERNAL,
        entity_type=EntityType.INVESTOR, entity_id=investor_id,
        detail={"target": "buy_box", "fields": sorted(fields.keys())},
    )
    return public_dict(investor)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


@router.patch("/me/password")
async def change_password(
    body: PasswordChange,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    investor = await get_investor(investor_id)
    if investor is None:
        raise AuthError("investor in token no longer exists")
    if not verify_password(body.current_password, investor.password):
        raise HTTPException(403, "current password is incorrect")
    await update_investor_fields(
        investor_id, password=hash_password(body.new_password)
    )
    get_audit().emit(
        investor_id=investor_id, actor="investor",
        kind=AuditKind.ACT_INTERNAL,
        entity_type=EntityType.INVESTOR, entity_id=investor_id,
        detail={"target": "password", "action": "change"},
    )
    return {"updated": True}


@router.delete("/me")
async def delete_me(
    investor_id: str = Depends(require_investor_id),
) -> dict:
    counts = await delete_investor_cascade(investor_id)
    if counts.get("investors", 0) == 0:
        raise HTTPException(404, "investor not found")
    return {"deleted": True, "investor_id": investor_id, "counts": counts}
