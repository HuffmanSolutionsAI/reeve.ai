from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.stubs import Vendor


async def get_vendor(vendor_id: str) -> Vendor | None:
    doc = await db()[COLLECTIONS["vendors"]].find_one({"_id": vendor_id})
    return Vendor.model_validate(doc) if doc else None


async def upsert_vendor(vendor: Vendor) -> Vendor:
    await db()[COLLECTIONS["vendors"]].replace_one(
        {"_id": vendor.id}, vendor.model_dump(by_alias=True), upsert=True,
    )
    return vendor


async def list_vendors_by_trade(investor_id: str, trade: str) -> list[Vendor]:
    cursor = db()[COLLECTIONS["vendors"]].find(
        {"investor_id": investor_id, "trades": trade, "active": True},
    )
    return [Vendor.model_validate(doc) async for doc in cursor]
