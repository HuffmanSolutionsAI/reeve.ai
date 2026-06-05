"""KPI computations over a list of transactions and a portfolio snapshot.

Pure functions — no IO. Callable from a tool or directly."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass


@dataclass
class KPIs:
    revenue: float
    expenses: float
    noi: float
    expense_ratio: float
    units_total: int
    occupancy: float | None
    revenue_per_unit: float
    noi_per_unit: float
    by_category: dict[str, float]
    period_days: int

    def to_dict(self) -> dict:
        return asdict(self)


def compute_kpis(
    *,
    transactions: list[dict],
    units_total: int,
    occupied_units: int | None = None,
    period_days: int = 30,
) -> KPIs:
    by_category: dict[str, float] = defaultdict(float)
    revenue = 0.0
    expenses = 0.0
    for t in transactions:
        amt = float(t.get("amount", 0.0))
        cat = t.get("category") or "other"
        by_category[cat] += amt
        if amt > 0:
            revenue += amt
        else:
            expenses += -amt
    noi = revenue - expenses
    return KPIs(
        revenue=round(revenue, 2),
        expenses=round(expenses, 2),
        noi=round(noi, 2),
        expense_ratio=round(expenses / revenue, 4) if revenue else 0.0,
        units_total=units_total,
        occupancy=round(occupied_units / units_total, 4) if (units_total and occupied_units is not None) else None,
        revenue_per_unit=round(revenue / units_total, 2) if units_total else 0.0,
        noi_per_unit=round(noi / units_total, 2) if units_total else 0.0,
        by_category={k: round(v, 2) for k, v in by_category.items()},
        period_days=period_days,
    )
