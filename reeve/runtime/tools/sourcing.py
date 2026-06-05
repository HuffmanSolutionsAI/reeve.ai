"""Sam's tools: dedupe against the existing pipeline + submit the sourcing
summary (which also persists the new Deal rows). The DuckDB query lives
in `pipeline.py` and is shared with anyone else who wants to read the
sourcing feed."""
from __future__ import annotations

from datetime import datetime, timezone

from ...contracts.sourcing_summary import SourcingSummary
from ...db.mongo import COLLECTIONS, db
from ...models.artifact import ArtifactType, Confidence
from ...models.deal import Deal, DealSource, DealStatus
from ...repos.artifacts import write_artifact
from ...repos.deals import upsert_deal
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "list_existing_deals",
    Tier.READ,
    {"type": "object", "properties": {}, "additionalProperties": False},
    (
        "Return every deal in the investor's pipeline with address + status, "
        "so Sam can dedupe candidates from the sourcing feed before "
        "surfacing them."
    ),
    reads=["deal"],
    needs_ctx=True,
)
async def list_existing_deals(_ctx: RunContext) -> dict:
    cursor = db()[COLLECTIONS["deals"]].find(
        {"investor_id": _ctx.investor_id},
        projection={"address": 1, "status": 1, "source": 1, "ask": 1, "units": 1},
    )
    deals = []
    async for d in cursor:
        deals.append({
            "id": d["_id"],
            "address": d["address"],
            "status": d.get("status"),
            "source": d.get("source"),
            "ask": d.get("ask"),
            "units": d.get("units"),
        })
    return {"deals": deals, "count": len(deals)}


def _normalize(addr: str) -> str:
    return " ".join(addr.lower().split())


@tool(
    "submit_sourcing_summary",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": (
                    "sourcing_summary payload matching "
                    "/contracts/sourcing_summary.schema.json"
                ),
            },
        },
        "required": ["artifact"],
        "additionalProperties": False,
    },
    (
        "Emit the sourcing_summary artifact AND persist any non-duplicate "
        "candidate as a Deal with source=sam, status=sourced. Sam's terminal "
        "tool — call to finish."
    ),
    reads=[],
    writes=["write_artifact", "create_deal"],
    terminal=True,
    needs_ctx=True,
)
async def submit_sourcing_summary(
    artifact: dict, _ctx: RunContext | None = None,
) -> dict:
    SourcingSummary.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None

    # Re-dedupe at submit time using the live pipeline — the LLM's marks
    # may have raced with another sourcing run.
    existing_addrs = set()
    async for d in db()[COLLECTIONS["deals"]].find(
        {"investor_id": _ctx.investor_id}, projection={"address": 1}
    ):
        existing_addrs.add(_normalize(d["address"]))

    surfaced = 0
    duplicates = 0
    for c in artifact.get("candidates", []):
        if _normalize(c["address"]) in existing_addrs:
            c["duplicate"] = True
            duplicates += 1
            continue
        deal = Deal(
            investor_id=_ctx.investor_id,
            address=c["address"],
            units=int(c.get("units", 0)) or None,
            ask=float(c.get("ask", 0)) or None,
            source=DealSource.SAM,
            status=DealStatus.SOURCED,
        )
        await upsert_deal(deal)
        c["deal_id"] = deal.id
        surfaced += 1
        existing_addrs.add(_normalize(c["address"]))

    artifact["surfaced"] = surfaced
    artifact["duplicates"] = duplicates

    written = await write_artifact(
        type=ArtifactType.SOURCING_SUMMARY,
        payload=artifact,
        produced_by=_ctx.agent_id or "sam",
        agent_run_id=_ctx.agent_run_id,
        confidence=Confidence(artifact["confidence"]),
        unverified=list(artifact.get("unverified", [])),
    )
    return {
        "type": "sourcing_summary",
        "artifact_id": written.id,
        "version": written.version,
        **artifact,
    }
