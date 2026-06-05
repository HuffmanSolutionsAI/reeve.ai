from __future__ import annotations

from pymongo import ReturnDocument

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.deal import Deal, DealStatus


async def get_deal(deal_id: str) -> Deal | None:
    doc = await db()[COLLECTIONS["deals"]].find_one({"_id": deal_id})
    return Deal.model_validate(doc) if doc else None


async def upsert_deal(deal: Deal) -> Deal:
    coll = db()[COLLECTIONS["deals"]]
    doc = deal.model_dump(by_alias=True)
    doc["updated_at"] = now_iso()
    await coll.replace_one({"_id": deal.id}, doc, upsert=True)
    return deal


async def set_deal_status(
    deal_id: str,
    status: DealStatus,
    *,
    latest_analysis_id: str | None = None,
) -> Deal | None:
    updates: dict = {
        "status": status.value if hasattr(status, "value") else str(status),
        "updated_at": now_iso(),
    }
    if latest_analysis_id is not None:
        updates["latest_analysis_id"] = latest_analysis_id
    doc = await db()[COLLECTIONS["deals"]].find_one_and_update(
        {"_id": deal_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return Deal.model_validate(doc) if doc else None
