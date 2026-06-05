from __future__ import annotations

from ...db.mongo import COLLECTIONS, db
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "get_portfolio_snapshot",
    Tier.READ,
    {"type": "object", "properties": {}, "additionalProperties": False},
    (
        "Return the investor's portfolio rolled up by building and unit, "
        "with totals + occupancy. Read-only."
    ),
    reads=["portfolio", "building", "unit"],
    needs_ctx=True,
)
async def get_portfolio_snapshot(_ctx: RunContext) -> dict:
    portfolios = []
    units_total = occupied = vacant = 0
    market_rent_sum = 0.0
    market_rent_n = 0

    async for p in db()[COLLECTIONS["portfolios"]].find({"investor_id": _ctx.investor_id}):
        buildings = []
        async for b in db()[COLLECTIONS["buildings"]].find({"portfolio_id": p["_id"]}):
            us = []
            async for u in db()[COLLECTIONS["units"]].find({"building_id": b["_id"]}):
                us.append({
                    "id": u["_id"],
                    "label": u["label"],
                    "status": u["status"],
                    "market_rent": u.get("market_rent"),
                })
                units_total += 1
                if u["status"] == "occupied":
                    occupied += 1
                elif u["status"] == "vacant":
                    vacant += 1
                if u.get("market_rent"):
                    market_rent_sum += float(u["market_rent"])
                    market_rent_n += 1
            buildings.append({
                "id": b["_id"], "address": b["address"],
                "units_count": b.get("units_count", len(us)),
                "basis": b.get("basis"), "acquired_at": b.get("acquired_at"),
                "units": us,
            })
        portfolios.append({"id": p["_id"], "name": p["name"], "buildings": buildings})

    return {
        "investor_id": _ctx.investor_id,
        "portfolios": portfolios,
        "totals": {
            "buildings": sum(len(p["buildings"]) for p in portfolios),
            "units": units_total,
            "occupied": occupied,
            "vacant": vacant,
            "occupancy": round(occupied / units_total, 4) if units_total else 0.0,
            "avg_market_rent": round(market_rent_sum / market_rent_n, 2) if market_rent_n else None,
        },
    }
