from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.stubs import Tenant


async def get_tenant(tenant_id: str) -> Tenant | None:
    doc = await db()[COLLECTIONS["tenants"]].find_one({"_id": tenant_id})
    return Tenant.model_validate(doc) if doc else None


async def upsert_tenant(tenant: Tenant) -> Tenant:
    await db()[COLLECTIONS["tenants"]].replace_one(
        {"_id": tenant.id}, tenant.model_dump(by_alias=True), upsert=True,
    )
    return tenant
