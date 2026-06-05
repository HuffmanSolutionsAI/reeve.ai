from __future__ import annotations

from pymongo import ReturnDocument

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.building import Building


async def create_building(building: Building) -> Building:
    await db()[COLLECTIONS["buildings"]].insert_one(building.model_dump(by_alias=True))
    return building


async def get_building(building_id: str) -> Building | None:
    doc = await db()[COLLECTIONS["buildings"]].find_one({"_id": building_id})
    return Building.model_validate(doc) if doc else None


async def list_buildings_in_portfolios(portfolio_ids: list[str]) -> list[Building]:
    if not portfolio_ids:
        return []
    cursor = db()[COLLECTIONS["buildings"]].find(
        {"portfolio_id": {"$in": portfolio_ids}}
    )
    return [Building.model_validate(doc) async for doc in cursor]


async def find_building_by_address(
    investor_id: str, address: str
) -> Building | None:
    """Walks investor → portfolios → buildings to look for a matching
    address. Case-insensitive, whitespace-collapsed compare."""
    from .portfolios import list_portfolios

    target = " ".join(address.strip().lower().split())
    portfolios = await list_portfolios(investor_id)
    portfolio_ids = [p.id for p in portfolios]
    for b in await list_buildings_in_portfolios(portfolio_ids):
        if " ".join(b.address.strip().lower().split()) == target:
            return b
    return None


async def update_building_fields(
    building_id: str, **fields: object
) -> Building | None:
    """Atomic partial update. `None`-valued kwargs are skipped."""
    updates: dict[str, object] = {
        k: v for k, v in fields.items() if v is not None
    }
    if not updates:
        return None
    updates["updated_at"] = now_iso()
    doc = await db()[COLLECTIONS["buildings"]].find_one_and_update(
        {"_id": building_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return Building.model_validate(doc) if doc else None


async def delete_building(building_id: str) -> int:
    result = await db()[COLLECTIONS["buildings"]].delete_one({"_id": building_id})
    return int(result.deleted_count)
