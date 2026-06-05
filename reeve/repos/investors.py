from __future__ import annotations

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
