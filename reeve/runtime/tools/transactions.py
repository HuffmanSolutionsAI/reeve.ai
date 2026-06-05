from __future__ import annotations

from ...repos.transactions import list_transactions as repo_list
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "list_transactions",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "period_start": {"type": "string", "description": "ISO date inclusive."},
            "period_end": {"type": "string", "description": "ISO date inclusive."},
            "building_id": {
                "type": "string",
                "description": "Optional. If omitted, all buildings for the investor.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 5000},
        },
        "required": ["period_start", "period_end"],
        "additionalProperties": False,
    },
    (
        "List categorized transactions for the investor in a date range. "
        "Reads the `transaction` collection — a sensitive read; every call "
        "writes an audit event."
    ),
    reads=["transaction"],
    needs_ctx=True,
)
async def list_transactions(
    period_start: str,
    period_end: str,
    building_id: str | None = None,
    limit: int = 500,
    _ctx: RunContext | None = None,
) -> dict:
    assert _ctx is not None
    txns = await repo_list(
        investor_id=_ctx.investor_id,
        building_id=building_id,
        period_start=period_start,
        period_end=period_end,
        limit=limit,
    )
    return {
        "transactions": txns,
        "count": len(txns),
        "period": {"start": period_start, "end": period_end},
        "building_id": building_id,
    }
