from __future__ import annotations

from ..capability import Tier
from ..tool import tool


@tool(
    "pull_comps",
    Tier.READ,
    {
        "type": "object",
        "properties": {"address": {"type": "string"}},
        "required": ["address"],
        "additionalProperties": False,
    },
    "Pull rent and sales comps for the area around an address.",
    reads=["comp"],
)
async def pull_comps(address: str) -> dict:
    return {
        "address": address,
        "avg_market_rent": 1466,
        "_stub": "real comps source wired in step 3",
    }
