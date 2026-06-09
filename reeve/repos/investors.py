from __future__ import annotations

from pymongo import ReturnDocument

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.investor import Investor


async def get_investor(investor_id: str) -> Investor | None:
    doc = await db()[COLLECTIONS["investors"]].find_one({"_id": investor_id})
    return Investor.model_validate(doc) if doc else None


async def get_investor_by_email(email: str) -> Investor | None:
    """Email is stored lowercased + stripped; normalize the query the same way."""
    norm = email.strip().lower()
    doc = await db()[COLLECTIONS["investors"]].find_one({"email": norm})
    return Investor.model_validate(doc) if doc else None


async def upsert_investor(investor: Investor) -> Investor:
    coll = db()[COLLECTIONS["investors"]]
    doc = investor.model_dump(by_alias=True)
    doc["updated_at"] = now_iso()
    await coll.replace_one({"_id": investor.id}, doc, upsert=True)
    return investor


async def update_investor_fields(
    investor_id: str, **fields: object
) -> Investor | None:
    """Atomic partial update of top-level investor fields. `None`-valued
    kwargs are skipped — pass only what should change."""
    updates: dict[str, object] = {
        k: v for k, v in fields.items() if v is not None
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


async def delete_investor_cascade(investor_id: str) -> dict[str, int]:
    """Wipe an investor and every entity scoped to them. Hard delete —
    intended for dev reset + GDPR-style requests, not soft retention.

    Cascade order matters because some collections key by an upstream id
    (units by building_id, messages by conversation_id, etc.). We resolve
    the upstream ids first, then delete leaf-to-root.

    Returns a count map of what was removed (zeroes included)."""
    handle = db()
    counts: dict[str, int] = {}

    # ---- resolve cascading ids -----------------------------------------
    portfolio_ids: list[str] = []
    async for p in handle[COLLECTIONS["portfolios"]].find(
        {"investor_id": investor_id}, projection={"_id": 1}
    ):
        portfolio_ids.append(p["_id"])

    building_ids: list[str] = []
    if portfolio_ids:
        async for b in handle[COLLECTIONS["buildings"]].find(
            {"portfolio_id": {"$in": portfolio_ids}}, projection={"_id": 1}
        ):
            building_ids.append(b["_id"])

    conversation_ids: list[str] = []
    async for c in handle[COLLECTIONS["conversations"]].find(
        {"investor_id": investor_id}, projection={"_id": 1}
    ):
        conversation_ids.append(c["_id"])

    agent_run_ids: list[str] = []
    if conversation_ids:
        async for r in handle[COLLECTIONS["agent_runs"]].find(
            {"conversation_id": {"$in": conversation_ids}}, projection={"_id": 1}
        ):
            agent_run_ids.append(r["_id"])

    # ---- delete (leaf → root) ------------------------------------------
    ops: list[tuple[str, dict | None]] = [
        ("units",        {"building_id": {"$in": building_ids}} if building_ids else None),
        ("buildings",    {"_id": {"$in": building_ids}} if building_ids else None),
        ("portfolios",   {"_id": {"$in": portfolio_ids}} if portfolio_ids else None),
        ("artifacts",    {"agent_run_id": {"$in": agent_run_ids}} if agent_run_ids else None),
        ("messages",     {"conversation_id": {"$in": conversation_ids}} if conversation_ids else None),
        ("agent_runs",   {"_id": {"$in": agent_run_ids}} if agent_run_ids else None),
        ("conversations", {"_id": {"$in": conversation_ids}} if conversation_ids else None),
        ("deals",        {"investor_id": investor_id}),
        ("transactions", {"investor_id": investor_id}),
        ("leases",       {"investor_id": investor_id}),
        ("tenants",      {"investor_id": investor_id}),
        ("vendors",      {"investor_id": investor_id}),
        ("proposals",    {"investor_id": investor_id}),
        ("audit_events", {"investor_id": investor_id}),
        ("investors",    {"_id": investor_id}),
    ]

    for collection_key, flt in ops:
        if flt is None:
            counts[collection_key] = 0
            continue
        result = await handle[COLLECTIONS[collection_key]].delete_many(flt)
        counts[collection_key] = int(result.deleted_count)

    return counts
