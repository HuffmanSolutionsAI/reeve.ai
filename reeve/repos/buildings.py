from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.building import Building


async def create_building(building: Building) -> Building:
    await db()[COLLECTIONS["buildings"]].insert_one(building.model_dump(by_alias=True))
    return building


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
