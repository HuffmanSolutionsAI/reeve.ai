"""property_analysis — real underwriting math.

Returns a structured analysis (metrics + rent_roll + assumptions +
max_clearing_price + threshold check) that Ana composes into the
deal_analysis artifact. Reads the investor's buy-box from ctx for the
threshold check; otherwise stateless."""
from __future__ import annotations

from ...repos.investors import get_investor
from ...underwriting import (
    FINANCING_DEFAULTS,
    OPEX_DEFAULTS,
    UnderwritingInputs,
    max_clearing_price,
    underwrite,
)
from ...underwriting.model import synthesize_rent_roll
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "property_analysis",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "address": {"type": "string"},
            "ask": {"type": "number"},
            "units": {"type": "integer", "minimum": 1},
            "avg_market_rent": {
                "type": "number",
                "description": "Market rent per unit per month (from pull_comps).",
            },
            "avg_in_place_rent": {
                "type": "number",
                "description": "Per-unit in-place rent if known (from a T-12 / rent roll).",
            },
            "rent_gap_pct": {
                "type": "number",
                "description": (
                    "If in-place is unknown, estimate it as market × (1 − this). "
                    "Default 0.10. Surface this assumption and lower confidence."
                ),
            },
            "vacancy": {"type": "number"},
            "mgmt_rate": {"type": "number"},
            "other_expense_rate": {
                "type": "number",
                "description": "Taxes + insurance + maintenance + utilities as % of EGI.",
            },
            "capex_per_unit": {"type": "number"},
            "interest_rate": {"type": "number"},
            "term_years": {"type": "integer"},
            "ltv": {"type": "number"},
        },
        "required": ["address", "ask", "units", "avg_market_rent"],
        "additionalProperties": False,
    },
    (
        "Underwrite a property. Returns cap (in-place + pro-forma), DSCR, "
        "CoC, rent upside, a synthesized rent roll, the assumptions used, "
        "and the max price at which the deal still clears the investor's "
        "buy-box thresholds."
    ),
    reads=["investor", "buy_box", "deal", "building", "unit"],
    needs_ctx=True,
)
async def property_analysis(
    address: str,
    ask: float,
    units: int,
    avg_market_rent: float,
    avg_in_place_rent: float | None = None,
    rent_gap_pct: float = 0.10,
    vacancy: float = OPEX_DEFAULTS["vacancy"],
    mgmt_rate: float = OPEX_DEFAULTS["mgmt_rate"],
    other_expense_rate: float = OPEX_DEFAULTS["other_expense_rate"],
    capex_per_unit: float = OPEX_DEFAULTS["capex_per_unit"],
    interest_rate: float = FINANCING_DEFAULTS["interest_rate"],
    term_years: int = FINANCING_DEFAULTS["term_years"],
    ltv: float = FINANCING_DEFAULTS["ltv"],
    _ctx: RunContext | None = None,
) -> dict:
    rent_roll = synthesize_rent_roll(
        units=units,
        avg_market_rent=avg_market_rent,
        avg_in_place_rent=avg_in_place_rent,
        rent_gap_pct=rent_gap_pct,
    )
    inputs = UnderwritingInputs(
        ask=ask,
        rent_roll=rent_roll,
        vacancy=vacancy,
        mgmt_rate=mgmt_rate,
        other_expense_rate=other_expense_rate,
        capex_per_unit=capex_per_unit,
        interest_rate=interest_rate,
        term_years=term_years,
        ltv=ltv,
    )
    result = underwrite(inputs)

    buy_box = None
    if _ctx is not None:
        investor = await get_investor(_ctx.investor_id)
        if investor is not None:
            buy_box = investor.buy_box

    cap_floor = buy_box.cap_floor if buy_box else None
    min_dscr = buy_box.min_dscr if buy_box else None
    target_coc = buy_box.target_coc if buy_box else None

    max_price = max_clearing_price(
        inputs,
        cap_floor=cap_floor,
        min_dscr=min_dscr,
        target_coc=target_coc,
    )
    clears_at_ask = (
        (cap_floor is None or result.cap_in_place >= cap_floor)
        and (min_dscr is None or result.dscr >= min_dscr)
        and (target_coc is None or result.coc_year1 >= target_coc)
    )

    rent_roll_payload = [
        {"unit": e.unit, "in_place": round(e.in_place, 2), "market": round(e.market, 2)}
        for e in rent_roll
    ]
    assumptions = [
        f"Vacancy {round(vacancy * 100)}%",
        f"Mgmt {round(mgmt_rate * 100)}%",
        f"Other OpEx {round(other_expense_rate * 100)}% of EGI",
        f"CapEx ${int(capex_per_unit)}/unit/yr",
        (
            f"{interest_rate * 100:.2f}% · {term_years}yr · "
            f"{round(ltv * 100)}% LTV"
        ),
    ]
    if avg_in_place_rent is None:
        assumptions.append(
            f"In-place rent estimated at market − {round(rent_gap_pct * 100)}%"
        )

    return {
        "address": address,
        "ask": ask,
        "units": units,
        "rent_roll": rent_roll_payload,
        "metrics": result.as_metrics(),
        "internals": {
            "noi_in_place": round(result.noi_in_place, 2),
            "noi_proforma": round(result.noi_proforma, 2),
            "annual_debt_service": round(result.annual_debt_service, 2),
            "monthly_pi": round(result.monthly_pi, 2),
            "egi_in_place": round(result.egi_in_place, 2),
            "egi_proforma": round(result.egi_proforma, 2),
            "opex_in_place": round(result.opex_in_place, 2),
        },
        "assumptions": assumptions,
        "buy_box": {
            "cap_floor": cap_floor,
            "min_dscr": min_dscr,
            "target_coc": target_coc,
        },
        "max_clearing_price": max_price,
        "clears_at_ask": clears_at_ask,
    }
