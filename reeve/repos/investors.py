from __future__ import annotations

from pymongo import ReturnDocument

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.investor import Investor


async def get_investor(investor_id: str) -> Investor | None:
    doc = await db()[COLLECTIONS["investors"]].find_one({"_id": investor_id})
    return Investor.model_validate(doc) if doc else None


async def upsert_investor(investor: Investor) -> Investor:
    coll = db()[COLLECTIONS["investors"]]
    doc = investor.model_dump(by_alias=True)
    doc["updated_at"] = now_iso()
    await coll.replace_one({"_id": investor.id}, doc, upsert=True)
    return investor


async def update_buy_box_fields(
    investor_id: str, **fields: object
) -> Investor | None:
    """Atomic partial update of buy_box.* fields. `None`-valued kwargs are
    skipped so the caller can pass everything the tool accepted; only the
    fields the user actually named are written. Returns the post-update
    investor (or None if not found / nothing to update)."""
    updates: dict[str, object] = {
        f"buy_box.{k}": v for k, v in fields.items() if v is not None
    }
    if not updates:
        return None
    updates["updated_at"] = now_iso()
    doc = await db()[COLLECTIONS["investors"]].find_one_and_update(
        {"_id": investor_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return Investor.model_validate(doc) if doc else None
