from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.stubs import Transaction


async def insert_transactions(txns: list[Transaction]) -> int:
    """Upsert by `plaid_id` so re-running a sync is idempotent. The existing
    row keeps its `_id` on update; new rows take the one from the model.
    Returns the count of rows inserted or modified."""
    if not txns:
        return 0
    coll = db()[COLLECTIONS["transactions"]]
    n = 0
    for t in txns:
        doc = t.model_dump(by_alias=True)
        new_id = doc.pop("_id")
        if doc.get("plaid_id"):
            result = await coll.update_one(
                {"plaid_id": doc["plaid_id"]},
                {"$set": doc, "$setOnInsert": {"_id": new_id}},
                upsert=True,
            )
            if result.upserted_id is not None or result.modified_count > 0:
                n += 1
        else:
            doc["_id"] = new_id
            await coll.insert_one(doc)
            n += 1
    return n


async def list_transactions(
    *,
    investor_id: str | None = None,
    building_id: str | None = None,
    period_start: str,
    period_end: str,
    limit: int = 500,
) -> list[dict]:
    query: dict = {"date": {"$gte": period_start, "$lte": period_end}}
    if investor_id:
        query["investor_id"] = investor_id
    if building_id:
        query["building_id"] = building_id
    cursor = (
        db()[COLLECTIONS["transactions"]]
        .find(query)
        .sort([("date", -1)])
        .limit(limit)
    )
    return [doc async for doc in cursor]
