from __future__ import annotations

from ...comps.source import lookup_comps
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
    (
        "Pull rent and sales comps for an address. Returns market rent, "
        "rent per sqft, median price per unit, and the sale-cap range, "
        "matched by ZIP then city. Result is cached in Mongo for 24h. "
        "If no market matches, returns matched=False — never fabricate a number."
    ),
    reads=["comp"],
)
async def pull_comps(address: str) -> dict:
    return await lookup_comps(address)
