from __future__ import annotations

from ..capability import Tier
from ..tool import tool


@tool(
    "property_analysis",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "address": {"type": "string"},
            "ask": {"type": "number"},
        },
        "required": ["address"],
        "additionalProperties": False,
    },
    "Run the underwriting model on a property and return key metrics.",
    reads=["deal", "building", "unit"],
)
async def property_analysis(address: str, ask: float | None = None) -> dict:
    return {
        "address": address,
        "ask": ask,
        "cap_in_place": 0.054,
        "cap_proforma": 0.069,
        "coc_year1": 0.041,
        "coc_stabilized": 0.087,
        "dscr": 1.24,
        "avg_rent_in_place": 1233,
        "avg_rent_market": 1466,
        "rent_upside_pct": 0.19,
        "rent_upside_monthly": 1866,
        "_stub": "real underwriter wired in step 3",
    }
