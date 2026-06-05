from __future__ import annotations

from ...repos.investors import get_investor, update_buy_box_fields
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


@tool(
    "update_buy_box",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "cap_floor": {
                "type": "number", "minimum": 0,
                "description": "Minimum cap rate, decimal (0.07 = 7%).",
            },
            "min_dscr": {
                "type": "number", "minimum": 0,
                "description": "Minimum debt-service coverage ratio.",
            },
            "target_coc": {
                "type": "number", "minimum": 0,
                "description": "Target cash-on-cash, decimal (0.08 = 8%).",
            },
            "markets": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "Replaces the markets list. Pass the FULL list you want, "
                    "not a delta — omit the field to leave the existing list "
                    "unchanged."
                ),
            },
            "unit_range": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
                "minItems": 2, "maxItems": 2,
                "description": "[min_units, max_units].",
            },
            "price_range": {
                "type": "array",
                "items": {"type": "number", "minimum": 0},
                "minItems": 2, "maxItems": 2,
                "description": "[min_ask, max_ask] in dollars.",
            },
        },
        "additionalProperties": False,
    },
    (
        "Patch the investor's buy-box. Only the fields explicitly passed "
        "are written; every other buy-box field is left untouched. Reeve "
        "uses this when the investor explicitly authorizes a change — "
        "never on its own initiative."
    ),
    reads=["investor"],
    writes=["update_investor_context"],
    needs_ctx=True,
)
async def update_buy_box(
    _ctx: RunContext,
    cap_floor: float | None = None,
    min_dscr: float | None = None,
    target_coc: float | None = None,
    markets: list[str] | None = None,
    unit_range: list[int] | None = None,
    price_range: list[float] | None = None,
) -> dict:
    investor = await update_buy_box_fields(
        _ctx.investor_id,
        cap_floor=cap_floor,
        min_dscr=min_dscr,
        target_coc=target_coc,
        markets=markets,
        unit_range=unit_range,
        price_range=price_range,
    )
    if investor is None:
        return {
            "updated": False,
            "reason": "investor not found or no fields to update",
        }
    changed = {
        k: v
        for k, v in {
            "cap_floor": cap_floor,
            "min_dscr": min_dscr,
            "target_coc": target_coc,
            "markets": markets,
            "unit_range": unit_range,
            "price_range": price_range,
        }.items()
        if v is not None
    }
    return {
        "updated": True,
        "investor_id": investor.id,
        "changed": changed,
        "buy_box": investor.buy_box.model_dump(),
    }
