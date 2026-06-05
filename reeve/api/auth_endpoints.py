"""Auth + identity endpoints.

Public:
  POST /api/auth/dev-token   — issue a token for an existing investor (dev path).
  POST /api/auth/signup      — create a new investor + return a token.

Authenticated:
  GET    /api/me                       — current investor.
  PATCH  /api/me                       — update name / entity_name / preferences.
  PATCH  /api/me/buy-box               — update buy-box (any subset of fields).
  DELETE /api/me                       — wipe the investor and everything
                                         scoped to them. Hard reset for dev /
                                         GDPR-style requests."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..audit import AuditKind, EntityType, get_audit
from ..models.investor import BuyBox, Investor, InvestorPreferences
from ..repos.investors import (
    delete_investor_cascade,
    get_investor,
    update_buy_box_fields,
    update_investor_fields,
    upsert_investor,
)
from .auth import AuthError, issue_token, require_investor_id


router = APIRouter()


# ---- dev-token ------------------------------------------------------------
class DevTokenRequest(BaseModel):
    investor_id: str


@router.post("/auth/dev-token")
async def dev_token(body: DevTokenRequest) -> dict:
    investor = await get_investor(body.investor_id)
    if investor is None:
        raise HTTPException(404, f"investor {body.investor_id!r} not found")
    return issue_token(body.investor_id)


# ---- signup ---------------------------------------------------------------
class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    entity_name: str | None = None
    buy_box: BuyBox | None = None
    preferences: InvestorPreferences | None = None


@router.post("/auth/signup")
async def signup(body: SignupRequest) -> dict:
    """Create a new investor and immediately issue a token. No auth — this
    is the only path that produces an investor without an existing one."""
    investor = Investor(
        name=body.name,
        entity_name=body.entity_name,
        buy_box=body.buy_box or BuyBox(),
        preferences=body.preferences or InvestorPreferences(),
    )
    await upsert_investor(investor)
    get_audit().emit(
        investor_id=investor.id,
        actor="investor",
        kind=AuditKind.ACT_INTERNAL,
        entity_type=EntityType.INVESTOR,
        entity_id=investor.id,
        detail={"target": "investor", "action": "signup"},
    )
    return issue_token(investor.id)


# ---- /me ------------------------------------------------------------------
@router.get("/me")
async def me(investor_id: str = Depends(require_investor_id)) -> dict:
    investor = await get_investor(investor_id)
    if investor is None:
        raise AuthError("investor in token no longer exists")
    return investor.model_dump(by_alias=True)


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
    return investor.model_dump(by_alias=True)


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
    """Same field semantics as the `update_buy_box` agent tool: only the
    fields you pass are written, the rest are left alone. Markets is a
    full-list replace, not a delta."""
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
    return investor.model_dump(by_alias=True)


@router.delete("/me")
async def delete_me(
    investor_id: str = Depends(require_investor_id),
) -> dict:
    """Wipe the investor + every entity scoped to them. The audit row for
    THIS deletion is intentionally not written (the audit collection is
    part of the wipe); the response carries the deletion counts so the
    UI can show what was cleared."""
    counts = await delete_investor_cascade(investor_id)
    if counts.get("investors", 0) == 0:
        raise HTTPException(404, "investor not found")
    return {"deleted": True, "investor_id": investor_id, "counts": counts}
