"""REST endpoints backing the UI surfaces: activity feed, pipeline,
portfolio, conversation hydration, artifact retrieval."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query

from ..audit import get_audit
from ..db.mongo import COLLECTIONS, db
from ..repos.conversations import get_conversation
from ..repos.investors import get_investor
from ..repos.messages import list_messages


router = APIRouter()


@router.get("/investors/{investor_id}")
async def investor(investor_id: str) -> dict:
    inv = await get_investor(investor_id)
    if inv is None:
        raise HTTPException(404, "investor not found")
    return inv.model_dump(by_alias=True)


@router.get("/activity")
async def activity(
    investor_id: str = Query(..., description="investor id"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    audit = get_audit()
    # The Mongo backend is sync (pymongo); run in a thread so we don't block
    # the event loop.
    events = await asyncio.to_thread(audit.feed, investor_id, limit=limit)
    return {"events": events, "investor_id": investor_id, "limit": limit}


@router.get("/pipeline")
async def pipeline(investor_id: str = Query(...)) -> dict:
    cursor = (
        db()[COLLECTIONS["deals"]]
        .find({"investor_id": investor_id})
        .sort([("updated_at", -1)])
    )
    by_status: dict[str, list[dict]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    async for doc in cursor:
        status = doc.get("status", "sourced")
        by_status[status].append(doc)
        counts[status] += 1
    return {
        "investor_id": investor_id,
        "by_status": by_status,
        "counts": counts,
        "total": sum(counts.values()),
    }


@router.get("/portfolio")
async def portfolio(investor_id: str = Query(...)) -> dict:
    portfolios_coll = db()[COLLECTIONS["portfolios"]]
    buildings_coll = db()[COLLECTIONS["buildings"]]
    units_coll = db()[COLLECTIONS["units"]]

    portfolios = []
    units_count = 0
    buildings_count = 0
    async for p in portfolios_coll.find({"investor_id": investor_id}):
        bs = []
        async for b in buildings_coll.find({"portfolio_id": p["_id"]}):
            us = await units_coll.find({"building_id": b["_id"]}).to_list(length=None)
            b["units"] = us
            bs.append(b)
            units_count += len(us)
            buildings_count += 1
        p["buildings"] = bs
        portfolios.append(p)

    return {
        "investor_id": investor_id,
        "portfolios": portfolios,
        "totals": {"buildings": buildings_count, "units": units_count},
    }


@router.get("/conversations/{conversation_id}/messages")
async def conversation_messages(conversation_id: str) -> dict:
    conv = await get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    messages = await list_messages(conversation_id)
    return {
        "conversation": conv.model_dump(by_alias=True),
        "messages": [m.model_dump(by_alias=True) for m in messages],
    }


@router.get("/artifacts/{artifact_id}")
async def artifact(artifact_id: str) -> dict:
    doc = await db()[COLLECTIONS["artifacts"]].find_one({"_id": artifact_id})
    if doc is None:
        raise HTTPException(404, "artifact not found")
    return doc
