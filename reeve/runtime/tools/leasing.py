"""Leo's tools: find vacant units, post a listing (GATED).

The post_listing handler at execution time 'posts' to each channel
(mocked — generates plausible listing URLs) and writes a listing
artifact with the URLs + posted_at."""
from __future__ import annotations

import hashlib
from urllib.parse import quote_plus

from ...contracts.listing import Listing
from ...db.mongo import COLLECTIONS, db
from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...repos.artifacts import write_artifact
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "list_vacant_units",
    Tier.READ,
    {"type": "object", "properties": {}, "additionalProperties": False},
    (
        "Return every vacant unit in the investor's portfolio with last "
        "lease end + market rent (so Leo can price the listing). Reads "
        "unit and lease — `lease` is sensitive, so the per-call read "
        "audit fires."
    ),
    reads=["building", "unit", "lease"],
    needs_ctx=True,
)
async def list_vacant_units(_ctx: RunContext) -> dict:
    assert _ctx is not None
    # Walk investor → portfolio → building → unit, then back-fill last
    # ended lease per vacant unit for an honest "days vacant" estimate.
    portfolios = [
        p async for p in db()[COLLECTIONS["portfolios"]].find(
            {"investor_id": _ctx.investor_id}
        )
    ]
    portfolio_ids = [p["_id"] for p in portfolios]
    buildings = [
        b async for b in db()[COLLECTIONS["buildings"]].find(
            {"portfolio_id": {"$in": portfolio_ids}}
        )
    ]
    by_building = {b["_id"]: b for b in buildings}

    vacant: list[dict] = []
    for b in buildings:
        async for u in db()[COLLECTIONS["units"]].find(
            {"building_id": b["_id"], "status": "vacant"}
        ):
            last_lease = await db()[COLLECTIONS["leases"]].find_one(
                {"unit_id": u["_id"], "status": "ended"},
                sort=[("term_end", -1)],
            )
            vacant.append({
                "unit_id": u["_id"],
                "label": u["label"],
                "building_id": b["_id"],
                "address": b["address"],
                "market_rent": u.get("market_rent"),
                "last_term_end": last_lease.get("term_end") if last_lease else None,
                "last_rent": last_lease.get("rent") if last_lease else None,
            })
    return {"units": vacant, "count": len(vacant)}


def _fake_url(channel: str, address: str, unit_label: str | None) -> str:
    slug = "-".join(
        filter(None, [address, f"unit-{unit_label}" if unit_label else None])
    ).lower().replace(" ", "-").replace(",", "")
    digest = hashlib.sha1(f"{channel}:{slug}".encode()).hexdigest()[:8]
    return f"https://www.{channel.replace('_', '.')}.example/listings/{quote_plus(slug)}-{digest}"


@tool(
    "post_listing",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "unit_id": {"type": "string"},
            "building_id": {"type": "string"},
            "asking_rent": {"type": "number", "minimum": 0},
            "deposit": {"type": "number"},
            "term_months": {"type": "integer", "minimum": 1, "maximum": 60},
            "available_from": {"type": "string", "description": "ISO date."},
            "headline": {"type": "string"},
            "description": {"type": "string"},
            "amenities": {"type": "array", "items": {"type": "string"}},
            "channels": {
                "type": "array",
                "items": {"enum": ["zillow", "apartments_com", "craigslist", "facebook_marketplace"]},
                "minItems": 1,
            },
        },
        "required": ["unit_id", "building_id", "asking_rent", "available_from",
                     "headline", "description", "channels"],
        "additionalProperties": False,
    },
    (
        "Post a listing for a vacant unit. GATED — the runner intercepts "
        "and queues a proposal; only execute_approved_proposal posts. The "
        "handler 'posts' to each channel (mocked in dev), generates "
        "listing URLs, and writes a listing artifact."
    ),
    reads=[],
    writes=["post_listing"],
)
async def post_listing(
    unit_id: str,
    building_id: str,
    asking_rent: float,
    available_from: str,
    headline: str,
    description: str,
    channels: list[str],
    deposit: float | None = None,
    term_months: int = 12,
    amenities: list[str] | None = None,
) -> dict:
    unit_doc = await db()[COLLECTIONS["units"]].find_one({"_id": unit_id})
    if unit_doc is None:
        raise ValueError(f"unit {unit_id!r} not found")
    if unit_doc.get("status") != "vacant":
        raise ValueError(
            f"unit {unit_doc.get('label')!r} is {unit_doc.get('status')!r}, not vacant"
        )
    building = await db()[COLLECTIONS["buildings"]].find_one({"_id": building_id})
    if building is None:
        raise ValueError(f"building {building_id!r} not found")

    posted_at = now_iso()
    listing_urls = {
        ch: _fake_url(ch, building["address"], unit_doc.get("label"))
        for ch in channels
    }
    payload = {
        "type": "listing",
        "unit_id": unit_id,
        "unit_label": unit_doc.get("label"),
        "building_id": building_id,
        "address": building.get("address"),
        "asking_rent": asking_rent,
        "deposit": deposit if deposit is not None else asking_rent,
        "term_months": term_months,
        "available_from": available_from,
        "headline": headline,
        "description": description,
        "amenities": list(amenities or []),
        "channels": list(channels),
        "posted_at": posted_at,
        "listing_urls": listing_urls,
    }
    Listing.model_validate(payload)

    artifact = await write_artifact(
        type=ArtifactType.LISTING,
        payload=payload,
        produced_by="leo",
        agent_run_id="execution_layer",
        confidence=Confidence.HIGH,
    )
    return {
        "posted": True,
        "posted_at": posted_at,
        "unit_id": unit_id,
        "channels": channels,
        "listing_urls": listing_urls,
        "artifact_id": artifact.id,
    }
