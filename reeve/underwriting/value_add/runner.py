"""Orchestrator — composes the NOI states, valuation band, financing
sizing, cross-checks, flags, sensitivity grid, and risk register into a
single `AnalysisResult` ready for the value_add_analysis artifact."""
from __future__ import annotations

from dataclasses import dataclass, field

from ...models.underwriting import (
    BrokerProforma,
    DealAssumptions,
    FinancingScenario,
    MarketContext,
    OperatingStatement,
    PropertyProfile,
    RenovationBudget,
    RentRoll,
)
from .costs import StabilizationCosts, cost_to_stabilize
from .cross_checks import CrossCheck, cross_check_panel
from .financing import FinancingSizing, size_financing
from .flags import Flag, detect_flags
from .noi import (
    BrokerDiffLine,
    NOIBreakdown,
    broker_proforma_diff,
    in_place_noi,
    stabilized_noi,
    stabilized_plus_ancillary_noi,
)
from .risk_register import AssumptionRisk, build_risk_register
from .sensitivity import SensitivityCell, sensitivity_grid
from .valuation import ValuationBand, valuation_band


@dataclass
class AnalysisInputs:
    """Bundle for the engine. The runner picks the financing scenario to
    use (caller passes the chosen one)."""
    rent_roll: RentRoll
    opex: OperatingStatement
    profile: PropertyProfile | None
    budget: RenovationBudget
    market: MarketContext
    financing: FinancingScenario
    assumptions: DealAssumptions
    broker_proforma: BrokerProforma | None = None
    bid_price: float = 0.0    # candidate bid for tax reassessment + DSCR


@dataclass
class AnalysisResult:
    noi_in_place: NOIBreakdown
    noi_stabilized: NOIBreakdown
    noi_stabilized_plus_ancillary: NOIBreakdown
    broker_diff: list[BrokerDiffLine]
    costs: StabilizationCosts
    band: ValuationBand
    financing: FinancingSizing
    cross_checks: list[CrossCheck]
    flags: list[Flag]
    sensitivity_cells: list[SensitivityCell]
    sensitivity_swing: float
    risk_register: list[AssumptionRisk]

    # Verdict + confidence are derived from the flags + the risk register.
    decision: str = "conditional"
    confidence: str = "low"
    headline: str = ""
    max_price: float = 0.0


def analyze(inp: AnalysisInputs) -> AnalysisResult:
    # --- choose the bid to use for tax reassessment ----------------------
    # Use the candidate bid if provided; else fall back to ceiling once it's
    # computed (chicken/egg — we use the candidate bid as the anchor).
    bid_for_taxes = inp.bid_price if inp.bid_price > 0 else inp.rent_roll.derived.units_total * 100_000

    # --- NOI states -------------------------------------------------------
    n1 = in_place_noi(inp.rent_roll, inp.opex, bid_price=bid_for_taxes)
    n2 = stabilized_noi(
        inp.rent_roll, inp.opex, inp.assumptions,
        bid_price=bid_for_taxes, profile=inp.profile,
    )
    n3 = stabilized_plus_ancillary_noi(n2, inp.assumptions)
    diff = broker_proforma_diff(inp.broker_proforma, n2)

    # --- cost-to-stabilize -----------------------------------------------
    costs = cost_to_stabilize(
        bid_price=bid_for_taxes,
        budget=inp.budget,
        financing=inp.financing,
        assumptions=inp.assumptions,
        in_place_noi_annual=n1.noi,
    )

    # --- valuation band ---------------------------------------------------
    band = valuation_band(
        in_place_noi=n1.noi,
        stabilized_noi=n2.noi,
        market_cap=inp.market.market_cap,
        exit_cap=inp.assumptions.exit_cap,
        cost_to_stabilize=costs.total,
        assumptions=inp.assumptions,
    )

    # --- financing sizing ------------------------------------------------
    occ = (
        inp.profile.physical_occupancy.value
        if inp.profile and inp.profile.physical_occupancy else 0.0
    )
    fin = size_financing(
        bid_price=bid_for_taxes,
        cost_to_stabilize_total=costs.total,
        stabilized_noi=n2.noi,
        stabilized_value=band.stabilized_value,
        in_place_physical_occupancy=occ,
        financing=inp.financing,
    )

    # --- cross-checks ----------------------------------------------------
    checks = cross_check_panel(
        bid=bid_for_taxes,
        units=inp.rent_roll.derived.units_total or 1,
        in_place_noi=n1.noi,
        stabilized_noi=n2.noi,
        gross_scheduled_income_annual=n1.gross_potential_income,
        cost_to_stabilize=costs.total,
        exit_cap=inp.assumptions.exit_cap,
        perm_dscr=fin.perm_dscr_at_stabilized if inp.financing.perm else None,
        perm_min_dscr=inp.financing.perm.min_dscr if inp.financing.perm else None,
    )

    # --- flags + sensitivity + risk register -----------------------------
    flags = detect_flags(
        rent_roll=inp.rent_roll, opex=inp.opex,
        profile=inp.profile, budget=inp.budget, market=inp.market,
        financing=inp.financing, assumptions=inp.assumptions,
        bid=bid_for_taxes,
    )
    cells, swing = sensitivity_grid(
        rent_roll=inp.rent_roll, opex=inp.opex,
        assumptions=inp.assumptions, profile=inp.profile,
        market_cap=inp.market.market_cap,
        cost_to_stabilize=costs.total,
        in_place_noi=n1.noi,
        bid_for_taxes=bid_for_taxes,
    )
    risks = build_risk_register(
        rent_roll=inp.rent_roll, opex=inp.opex,
        assumptions=inp.assumptions, profile=inp.profile,
        market_cap=inp.market.market_cap,
        cost_to_stabilize=costs.total,
        in_place_noi_value=n1.noi,
        bid_for_taxes=bid_for_taxes,
    )

    # --- verdict ---------------------------------------------------------
    blocking = [f for f in flags if f.severity == "blocking"]
    if blocking:
        decision = "conditional"
        confidence = "low"
        headline = (
            f"Conditional pursuit at ≤ ${band.walk_away:,.0f}; "
            f"{len(blocking)} blocking flag{'s' if len(blocking) != 1 else ''} must clear before a confident bid."
        )
    else:
        decision = "pursue" if band.walk_away > 0 else "pass"
        confidence = "medium"
        headline = f"Pursue at ≤ ${band.walk_away:,.0f}; opening at ${band.opening:,.0f}."

    return AnalysisResult(
        noi_in_place=n1,
        noi_stabilized=n2,
        noi_stabilized_plus_ancillary=n3,
        broker_diff=diff,
        costs=costs,
        band=band,
        financing=fin,
        cross_checks=checks,
        flags=flags,
        sensitivity_cells=cells,
        sensitivity_swing=swing,
        risk_register=risks,
        decision=decision,
        confidence=confidence,
        headline=headline,
        max_price=band.walk_away,
    )
