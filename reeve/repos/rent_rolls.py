"""Rent-roll repo. Staged collection — ingest writes a new doc per pass;
human confirmation promotes one to active by setting human_confirmed +
the deal's active_rent_roll_id pointer."""
from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.underwriting import RentRoll, recompute_derived


async def get_rent_roll(rent_roll_id: str) -> RentRoll | None:
    doc = await db()[COLLECTIONS["rent_rolls"]].find_one({"_id": rent_roll_id})
    return RentRoll.model_validate(doc) if doc else None


async def insert_rent_roll(rr: RentRoll) -> RentRoll:
    """Insert a new (staged) rent roll. Derived stats are computed at write."""
    rr.derived = recompute_derived(rr)
    await db()[COLLECTIONS["rent_rolls"]].insert_one(rr.model_dump(by_alias=True))
    return rr


async def list_rent_rolls_for_deal(deal_id: str) -> list[RentRoll]:
    cursor = (
        db()[COLLECTIONS["rent_rolls"]]
        .find({"deal_id": deal_id})
        .sort([("as_of", -1)])
    )
    return [RentRoll.model_validate(doc) async for doc in cursor]


async def confirm_rent_roll(rent_roll_id: str, *, confirmer_id: str) -> RentRoll | None:
    """Human confirmation: marks confirmed; the caller is responsible for
    flipping `deal.active_rent_roll_id` separately. Returns the post-update
    doc; None if not found."""
    from pymongo import ReturnDocument

    doc = await db()[COLLECTIONS["rent_rolls"]].find_one_and_update(
        {"_id": rent_roll_id},
        {"$set": {
            "human_confirmed": True,
            "confirmed_by": confirmer_id,
            "confirmed_at": now_iso(),
            "updated_at": now_iso(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    return RentRoll.model_validate(doc) if doc else None
