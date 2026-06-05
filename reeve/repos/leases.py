from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.stubs import Lease, LeaseStatus


async def get_lease(lease_id: str) -> Lease | None:
    doc = await db()[COLLECTIONS["leases"]].find_one({"_id": lease_id})
    return Lease.model_validate(doc) if doc else None


async def upsert_lease(lease: Lease) -> Lease:
    await db()[COLLECTIONS["leases"]].replace_one(
        {"_id": lease.id}, lease.model_dump(by_alias=True), upsert=True,
    )
    return lease


async def active_lease_for_unit(unit_id: str) -> Lease | None:
    """Most recent active lease on a unit. Pending leases don't count."""
    doc = await db()[COLLECTIONS["leases"]].find_one(
        {"unit_id": unit_id, "status": LeaseStatus.ACTIVE.value},
        sort=[("term_start", -1)],
    )
    return Lease.model_validate(doc) if doc else None
