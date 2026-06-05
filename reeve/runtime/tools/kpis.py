from __future__ import annotations

from ...finance.kpis import compute_kpis as _compute
from ..capability import Tier
from ..tool import tool


@tool(
    "compute_kpis",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "number"},
                        "category": {"type": "string"},
                    },
                },
                "description": "Transactions returned by list_transactions.",
            },
            "units_total": {"type": "integer", "minimum": 0},
            "occupied_units": {"type": "integer", "minimum": 0},
            "period_days": {"type": "integer", "minimum": 1},
        },
        "required": ["transactions", "units_total"],
        "additionalProperties": False,
    },
    (
        "Aggregate transactions into KPIs (revenue, expenses, NOI, expense "
        "ratio, occupancy, per-unit metrics, and by-category totals). Pure "
        "computation — no IO, no scope reads."
    ),
    reads=[],
)
def compute_kpis(
    transactions: list[dict],
    units_total: int,
    occupied_units: int | None = None,
    period_days: int = 30,
) -> dict:
    return _compute(
        transactions=transactions,
        units_total=units_total,
        occupied_units=occupied_units,
        period_days=period_days,
    ).to_dict()
