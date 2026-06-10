"""Operating-statement repo. Staged collection — same lifecycle pattern
as rent_rolls."""
from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.underwriting import OperatingStatement


async def get_operating_statement(opex_id: str) -> OperatingStatement | None:
    doc = await db()[COLLECTIONS["operating_statements"]].find_one({"_id": opex_id})
    return OperatingStatement.model_validate(doc) if doc else None


async def insert_operating_statement(opex: OperatingStatement) -> OperatingStatement:
    await db()[COLLECTIONS["operating_statements"]].insert_one(opex.model_dump(by_alias=True))
    return opex


async def list_operating_statements_for_deal(deal_id: str) -> list[OperatingStatement]:
    cursor = (
        db()[COLLECTIONS["operating_statements"]]
        .find({"deal_id": deal_id})
        .sort([("period.end", -1)])
    )
    return [OperatingStatement.model_validate(doc) async for doc in cursor]


async def confirm_operating_statement(
    opex_id: str, *, confirmer_id: str
) -> OperatingStatement | None:
    from pymongo import ReturnDocument

    doc = await db()[COLLECTIONS["operating_statements"]].find_one_and_update(
        {"_id": opex_id},
        {"$set": {
            "human_confirmed": True,
            "confirmed_by": confirmer_id,
            "confirmed_at": now_iso(),
            "updated_at": now_iso(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    return OperatingStatement.model_validate(doc) if doc else None
