"""Cash-flow underwriting math.

All percentages are decimals (0.05 = 5%). Inputs are deliberately explicit:
the agent supplies them so every assumption is captured in the artifact."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


OPEX_DEFAULTS = {
    "vacancy": 0.05,
    "mgmt_rate": 0.08,
    # Taxes + insurance + maintenance + utilities, as % of EGI.
    # 0.35 is conservative for older multifamily post-reassessment.
    "other_expense_rate": 0.35,
    # CapEx reserve per unit per year.
    "capex_per_unit": 300.0,
}

FINANCING_DEFAULTS = {
    "interest_rate": 0.0675,
    "term_years": 25,
    "ltv": 0.70,
}


@dataclass(frozen=True)
class RentRollEntry:
    unit: str
    in_place: float
    market: float


@dataclass
class UnderwritingInputs:
    ask: float
    rent_roll: list[RentRollEntry]
    vacancy: float = OPEX_DEFAULTS["vacancy"]
    mgmt_rate: float = OPEX_DEFAULTS["mgmt_rate"]
    other_expense_rate: float = OPEX_DEFAULTS["other_expense_rate"]
    capex_per_unit: float = OPEX_DEFAULTS["capex_per_unit"]
    interest_rate: float = FINANCING_DEFAULTS["interest_rate"]
    term_years: int = FINANCING_DEFAULTS["term_years"]
    ltv: float = FINANCING_DEFAULTS["ltv"]


@dataclass
class UnderwritingResult:
    # Matches the deal_analysis.metrics shape exactly.
    cap_in_place: float
    cap_proforma: float
    coc_year1: float
    coc_stabilized: float
    dscr: float
    avg_rent_in_place: float
    avg_rent_market: float
    rent_upside_pct: float
    rent_upside_monthly: float
    # Internals (useful for the agent's narrative; not in the contract).
    noi_in_place: float
    noi_proforma: float
    annual_debt_service: float
    monthly_pi: float
    egi_in_place: float
    egi_proforma: float
    opex_in_place: float

    def as_metrics(self) -> dict:
        return {
            "cap_in_place": round(self.cap_in_place, 4),
            "cap_proforma": round(self.cap_proforma, 4),
            "coc_year1": round(self.coc_year1, 4),
            "coc_stabilized": round(self.coc_stabilized, 4),
            "dscr": round(self.dscr, 2),
            "avg_rent_in_place": round(self.avg_rent_in_place, 2),
            "avg_rent_market": round(self.avg_rent_market, 2),
            "rent_upside_pct": round(self.rent_upside_pct, 4),
            "rent_upside_monthly": round(self.rent_upside_monthly, 2),
        }


def _monthly_payment(loan: float, monthly_rate: float, n_months: int) -> float:
    if monthly_rate <= 0:
        return loan / n_months
    return loan * monthly_rate / (1 - (1 + monthly_rate) ** -n_months)


def _expenses(egi: float, units: int, inp: UnderwritingInputs) -> float:
    return (
        egi * inp.mgmt_rate
        + egi * inp.other_expense_rate
        + inp.capex_per_unit * units
    )


def underwrite(inp: UnderwritingInputs) -> UnderwritingResult:
    units = len(inp.rent_roll)
    if units == 0:
        raise ValueError("rent_roll cannot be empty")

    monthly_in_place = sum(e.in_place for e in inp.rent_roll)
    monthly_market = sum(e.market for e in inp.rent_roll)
    gpi_in = monthly_in_place * 12
    gpi_pro = monthly_market * 12
    egi_in = gpi_in * (1 - inp.vacancy)
    egi_pro = gpi_pro * (1 - inp.vacancy)
    opex_in = _expenses(egi_in, units, inp)
    opex_pro = _expenses(egi_pro, units, inp)
    noi_in = egi_in - opex_in
    noi_pro = egi_pro - opex_pro

    cap_in = noi_in / inp.ask if inp.ask else 0.0
    cap_pro = noi_pro / inp.ask if inp.ask else 0.0

    loan = inp.ask * inp.ltv
    monthly_rate = inp.interest_rate / 12
    n_months = inp.term_years * 12
    monthly_pi = _monthly_payment(loan, monthly_rate, n_months)
    annual_ds = monthly_pi * 12

    dscr = noi_in / annual_ds if annual_ds > 0 else float("inf")
    down = inp.ask * (1 - inp.ltv)
    coc_year1 = (noi_in - annual_ds) / down if down > 0 else 0.0
    coc_stab = (noi_pro - annual_ds) / down if down > 0 else 0.0

    avg_in = monthly_in_place / units
    avg_market = monthly_market / units
    rent_upside_monthly = monthly_market - monthly_in_place
    rent_upside_pct = (
        rent_upside_monthly / monthly_in_place if monthly_in_place > 0 else 0.0
    )

    return UnderwritingResult(
        cap_in_place=cap_in,
        cap_proforma=cap_pro,
        coc_year1=coc_year1,
        coc_stabilized=coc_stab,
        dscr=dscr,
        avg_rent_in_place=avg_in,
        avg_rent_market=avg_market,
        rent_upside_pct=rent_upside_pct,
        rent_upside_monthly=rent_upside_monthly,
        noi_in_place=noi_in,
        noi_proforma=noi_pro,
        annual_debt_service=annual_ds,
        monthly_pi=monthly_pi,
        egi_in_place=egi_in,
        egi_proforma=egi_pro,
        opex_in_place=opex_in,
    )


def synthesize_rent_roll(
    units: int,
    avg_market_rent: float,
    avg_in_place_rent: float | None = None,
    rent_gap_pct: float = 0.10,
) -> list[RentRollEntry]:
    """Generate a {1A, 1B, 2A, …} rent roll when only averages are known.

    Assumes 2 units per floor. If `avg_in_place_rent` is None, in-place is
    estimated as `market * (1 - rent_gap_pct)` — a labeled assumption Ana
    must surface in the artifact and in her confidence."""
    if avg_in_place_rent is None:
        avg_in_place_rent = avg_market_rent * (1 - rent_gap_pct)
    labels: list[str] = []
    floor = 1
    side = 0
    for _ in range(units):
        labels.append(f"{floor}{'AB'[side]}")
        side += 1
        if side == 2:
            side = 0
            floor += 1
    return [
        RentRollEntry(unit=label, in_place=avg_in_place_rent, market=avg_market_rent)
        for label in labels
    ]
