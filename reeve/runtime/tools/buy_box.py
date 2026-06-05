from __future__ import annotations

from ...repos.investors import get_investor
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "get_buy_box",
    Tier.READ,
    {"type": "object", "properties": {}, "additionalProperties": False},
    "Return the investor's buy-box (cap floor, min DSCR, target CoC, markets).",
    reads=["investor", "buy_box"],
    needs_ctx=True,
)
async def get_buy_box(_ctx: RunContext) -> dict:
    investor = await get_investor(_ctx.investor_id)
    if investor is None:
        return {}
    return investor.buy_box.model_dump()
