"""Staged-document review + confirmation endpoints.

This is the human side of the ingestion gate (§8): agents can only write
staged documents; these investor-authenticated endpoints are the ONLY
path to `human_confirmed=True` and to the deal's `active_*_id` pointer.
Mechanically the same trust boundary as proposal approval.

  GET  /api/documents/pending                      — everything awaiting review
  GET  /api/rent-rolls/{id}                        — full detail for the review table
  GET  /api/operating-statements/{id}              — same
  POST /api/rent-rolls/{id}/confirm                — confirm + activate
  POST /api/operating-statements/{id}/confirm      — confirm + activate
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..audit import AuditKind, EntityType, get_audit
from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..repos.operating_statements import confirm_operating_statement, get_operating_statement
from ..repos.rent_rolls import confirm_rent_roll, get_rent_roll
from .auth import require_investor_id


router = APIRouter()


@router.get("/documents/pending")
async def pending_documents(
    investor_id: str = Depends(require_investor_id),
) -> dict:
    """Unconfirmed staged documents for the investor, newest first, with
    enough summary detail for the review card."""
    rolls = []
    async for doc in (
        db()[COLLECTIONS["rent_rolls"]]
        .find({"investor_id": investor_id, "human_confirmed": False})
        .sort([("created_at", -1)])
    ):
        deal = await db()[COLLECTIONS["deals"]].find_one(
            {"_id": doc["deal_id"]}, projection={"address": 1},
        )
        rolls.append({
            "id": doc["_id"],
            "deal_id": doc["deal_id"],
            "deal_address": (deal or {}).get("address"),
            "as_of": doc.get("as_of"),
            "derived": doc.get("derived", {}),
            "validation": doc.get("validation", {}),
            "source": doc.get("source", {}),
            "created_at": doc.get("created_at"),
        })

    statements = []
    async for doc in (
        db()[COLLECTIONS["operating_statements"]]
        .find({"investor_id": investor_id, "human_confirmed": False})
        .sort([("created_at", -1)])
    ):
        deal = await db()[COLLECTIONS["deals"]].find_one(
            {"_id": doc["deal_id"]}, projection={"address": 1},
        )
        annual_total = sum(
            (line.get("annual") or {}).get("value", 0.0)
            for line in doc.get("lines", [])
        )
        statements.append({
            "id": doc["_id"],
            "deal_id": doc["deal_id"],
            "deal_address": (deal or {}).get("address"),
            "period": doc.get("period", {}),
            "annual_total": round(annual_total, 2),
            "line_count": len(doc.get("lines", [])),
            "validation": doc.get("validation", {}),
            "source": doc.get("source", {}),
            "created_at": doc.get("created_at"),
        })

    return {"rent_rolls": rolls, "operating_statements": statements}


@router.get("/rent-rolls/{rent_roll_id}")
async def rent_roll_detail(
    rent_roll_id: str,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    rr = await get_rent_roll(rent_roll_id)
    if rr is None or rr.investor_id != investor_id:
        raise HTTPException(404, "rent roll not found")
    return rr.model_dump(by_alias=True)


@router.get("/operating-statements/{opex_id}")
async def operating_statement_detail(
    opex_id: str,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    opex = await get_operating_statement(opex_id)
    if opex is None or opex.investor_id != investor_id:
        raise HTTPException(404, "operating statement not found")
    return opex.model_dump(by_alias=True)


@router.post("/rent-rolls/{rent_roll_id}/confirm")
async def confirm_rent_roll_endpoint(
    rent_roll_id: str,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    rr = await get_rent_roll(rent_roll_id)
    if rr is None or rr.investor_id != investor_id:
        raise HTTPException(404, "rent roll not found")
    if rr.human_confirmed:
        raise HTTPException(400, "already confirmed")

    confirmed = await confirm_rent_roll(rent_roll_id, confirmer_id=investor_id)
    # Activate: this confirmation is what flips the deal pointer — the
    # ingestion tool cannot do it.
    await db()[COLLECTIONS["deals"]].update_one(
        {"_id": rr.deal_id},
        {"$set": {"active_rent_roll_id": rent_roll_id, "updated_at": now_iso()}},
    )
    get_audit().emit(
        investor_id=investor_id, actor="investor",
        kind=AuditKind.APPROVED,
        entity_type=EntityType.RENT_ROLL, entity_id=rent_roll_id,
        detail={"action": "confirm_rent_roll", "deal_id": rr.deal_id},
    )
    return {
        "confirmed": True,
        "rent_roll_id": rent_roll_id,
        "deal_id": rr.deal_id,
        "active": True,
        "derived": confirmed.derived.model_dump() if confirmed else None,
    }


@router.post("/operating-statements/{opex_id}/confirm")
async def confirm_operating_statement_endpoint(
    opex_id: str,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    opex = await get_operating_statement(opex_id)
    if opex is None or opex.investor_id != investor_id:
        raise HTTPException(404, "operating statement not found")
    if opex.human_confirmed:
        raise HTTPException(400, "already confirmed")

    await confirm_operating_statement(opex_id, confirmer_id=investor_id)
    await db()[COLLECTIONS["deals"]].update_one(
        {"_id": opex.deal_id},
        {"$set": {"active_operating_statement_id": opex_id, "updated_at": now_iso()}},
    )
    get_audit().emit(
        investor_id=investor_id, actor="investor",
        kind=AuditKind.APPROVED,
        entity_type=EntityType.OPERATING_STATEMENT, entity_id=opex_id,
        detail={"action": "confirm_operating_statement", "deal_id": opex.deal_id},
    )
    return {"confirmed": True, "operating_statement_id": opex_id, "deal_id": opex.deal_id, "active": True}
