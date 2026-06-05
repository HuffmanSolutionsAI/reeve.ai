from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.unit import Unit, UnitStatus


def generate_unit_labels(units_count: int, units_per_floor: int = 2) -> list[str]:
    """Make '1A', '1B', '2A', '2B', … labels for `units_count` units with
    `units_per_floor` per floor. Letter sequence is A–Z then AA, AB, …
    (anyone with >26 units per floor needs a custom label list anyway)."""
    if units_count < 1:
        return []
    per = max(units_per_floor, 1)
    labels: list[str] = []
    for i in range(units_count):
        floor = (i // per) + 1
        idx = i % per
        if idx < 26:
            letter = chr(ord("A") + idx)
        else:
            letter = "A" + chr(ord("A") + (idx - 26))
        labels.append(f"{floor}{letter}")
    return labels


async def create_units_bulk(
    *,
    building_id: str,
    labels: list[str],
    market_rent: float | None = None,
    initial_status: UnitStatus = UnitStatus.VACANT,
) -> list[Unit]:
    """Create one Unit per label. Returns the inserted units (in order)."""
    if not labels:
        return []
    units: list[Unit] = [
        Unit(
            building_id=building_id,
            label=label,
            market_rent=market_rent,
            status=initial_status,
        )
        for label in labels
    ]
    docs = [u.model_dump(by_alias=True) for u in units]
    await db()[COLLECTIONS["units"]].insert_many(docs)
    return units


async def list_unit_ids_for_building(building_id: str) -> list[str]:
    cursor = db()[COLLECTIONS["units"]].find(
        {"building_id": building_id}, projection={"_id": 1}
    )
    return [doc["_id"] async for doc in cursor]


async def delete_units_for_building(building_id: str) -> int:
    result = await db()[COLLECTIONS["units"]].delete_many(
        {"building_id": building_id}
    )
    return int(result.deleted_count)
