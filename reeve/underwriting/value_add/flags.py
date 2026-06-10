"""Blocking diligence flags (§6 of the data-model doc).

Each flag has a deterministic trigger; while ANY blocking flag is open,
the engine forces `verdict.decision='conditional'` and caps confidence
at 'low'. The artifact lists the open flags + their unblock actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...models.underwriting import (
    CONTINGENCY_FLOOR_BASE,
    AbatementAllowance,
    DealAssumptions,
    FinancingScenario,
    InsuranceRecord,
    MarketContext,
    OperatingStatement,
    PropertyProfile,
    RenovationBudget,
    RentRoll,
    TaxRecord,
)


@dataclass
class Flag:
    code: str
    severity: str           # "blocking" | "watch"
    text: str
    unblock_action: str | None = None


# ---- individual checks --------------------------------------------------
def _unconfirmed_extraction(rr: RentRoll, opex: OperatingStatement) -> Flag | None:
    if not rr.human_confirmed:
        return Flag(
            code="unconfirmed_extraction",
            severity="blocking",
            text="Rent roll has not been human-confirmed.",
            unblock_action="Investor or operator must review extracted rows vs. source PDF and confirm.",
        )
    if not opex.human_confirmed:
        return Flag(
            code="unconfirmed_extraction",
            severity="blocking",
            text="Operating statement has not been human-confirmed.",
            unblock_action="Confirm extracted T-12 line items.",
        )
    return None


def _achieved_rent_unverified(
    rr: RentRoll, assumptions: DealAssumptions,
) -> Flag | None:
    n = rr.derived.achieved_renovated.n
    if not assumptions.target_rents:
        return None
    if n < 3:
        return Flag(
            code="achieved_rent_unverified",
            severity="blocking",
            text=f"Target rent leans on {n} achieved-renovated observations; sample size too small to anchor stabilized NOI.",
            unblock_action="Lease audit on additional renovated-occupied units, or step target rent down to documented achieved.",
        )
    return None


def _below_agency_gate(
    profile: PropertyProfile | None, financing: FinancingScenario,
) -> Flag | None:
    if profile is None or profile.physical_occupancy is None or financing.perm is None:
        return None
    occ = profile.physical_occupancy.value
    gate = financing.perm.occupancy_gate
    if not gate.met_by(occ):
        return Flag(
            code="below_agency_gate",
            severity="blocking",
            text=f"Current physical occupancy {occ:.0%} below perm gate ({gate.occupancy:.0%} for {gate.days}d). Perm-first structure disqualified.",
            unblock_action="Acknowledge a bridge-to-perm path; once occupancy gate is met for the required hold, refi closes.",
        )
    return None


def _pre_1980_structure(
    profile: PropertyProfile | None, budget: RenovationBudget,
) -> Flag | None:
    if profile is None or not profile.has_pre_1980_structure:
        return None
    if budget.abatement.tested:
        return None
    return Flag(
        code="pre_1980_structure",
        severity="blocking",
        text=f"Pre-1980 structure (oldest {profile.oldest_year_built}); abatement allowance is assumed, not tested.",
        unblock_action="Asbestos/lead test results, or convert allowance to a tested verified line.",
    )


def _tax_reassessment_missing(opex: OperatingStatement, bid: float) -> Flag | None:
    if opex.tax.reassessed_at(bid) is not None:
        return None
    return Flag(
        code="tax_reassessment_missing",
        severity="blocking",
        text="No tax reassessment estimate at the candidate bid price.",
        unblock_action="County assessor estimate at trade price, or millage × price formula on record.",
    )


def _insurance_below_commercial(opex: OperatingStatement) -> Flag | None:
    ins = opex.insurance
    if ins.commercial_quote is not None:
        return None
    if ins.current_annual is None:
        return Flag(
            code="insurance_below_commercial",
            severity="blocking",
            text="No commercial insurance quote on file (and no current carrier figure).",
            unblock_action="Bind a commercial quote for a 5+ unit asset.",
        )
    return Flag(
        code="insurance_below_commercial",
        severity="blocking",
        text="Using current annual insurance; no commercial quote in hand.",
        unblock_action="Indicated commercial quote — residential-rate proxy is invalid for 5+ units.",
    )


def _valued_on_unachieved_proforma(
    rr: RentRoll, assumptions: DealAssumptions,
) -> Flag | None:
    """If any target rent exceeds achieved renovated mean by > 15%, the
    deal is partially valued on income it has never produced."""
    achieved = rr.derived.achieved_renovated.mean
    if achieved is None or not assumptions.target_rents:
        return None
    highest_target = max(t.monthly_rent for t in assumptions.target_rents)
    if highest_target > achieved * 1.15:
        return Flag(
            code="valued_on_unachieved_proforma",
            severity="blocking",
            text=f"Highest target rent (${highest_target:.0f}) is {(highest_target / achieved - 1):.0%} over achieved renovated mean (${achieved:.0f}).",
            unblock_action="Add renovated comps at the target price point, or step target down to documented achieved.",
        )
    return None


def _stale_rent_roll(rr: RentRoll) -> Flag | None:
    try:
        as_of = date.fromisoformat(rr.as_of)
        if (date.today() - as_of).days > 60:
            return Flag(
                code="stale_rent_roll",
                severity="watch",
                text=f"Rent roll as_of {rr.as_of} is more than 60 days old.",
                unblock_action="Re-ingest the current rent roll.",
            )
    except Exception:
        pass
    return None


def _hbu_question(
    profile: PropertyProfile | None, assumptions: DealAssumptions,
) -> Flag | None:
    if profile is None:
        return None
    if any(
        s.structure_type == "clubhouse" or (
            hasattr(s.structure_type, "value") and s.structure_type.value == "clubhouse"
        )
        for s in profile.structures
    ):
        # Clubhouse present — is conversion in the upside?
        if any(
            a.item == "clubhouse_conversion" or (
                hasattr(a.item, "value") and a.item.value == "clubhouse_conversion"
            )
            for a in assumptions.ancillary
        ):
            return Flag(
                code="hbu_question",
                severity="watch",
                text="Clubhouse → unit conversion is in the upside; HBU decision pending.",
                unblock_action="Investor decision: conversion vs. amenity. Record in deal assumptions.",
            )
    return None


def _contingency_below_floor(
    profile: PropertyProfile | None, budget: RenovationBudget,
) -> Flag | None:
    has_pre_1980 = profile.has_pre_1980_structure if profile else False
    systems_untested = any(
        (s.status == "contingent" or (hasattr(s.status, "value") and s.status.value == "contingent"))
        for s in budget.systems
    )
    floor = budget.required_contingency_floor(
        has_pre_1980=has_pre_1980, systems_untested=systems_untested,
    )
    if budget.contingency_pct < floor:
        return Flag(
            code="contingency_below_floor",
            severity="blocking",
            text=f"Contingency {budget.contingency_pct:.0%} below required floor {floor:.0%} (age + systems flags applied).",
            unblock_action="Raise contingency to floor or above, OR test systems / abatement to lower the floor.",
        )
    return None


# ---- aggregate ---------------------------------------------------------
def detect_flags(
    *,
    rent_roll: RentRoll,
    opex: OperatingStatement,
    profile: PropertyProfile | None,
    budget: RenovationBudget,
    market: MarketContext,
    financing: FinancingScenario,
    assumptions: DealAssumptions,
    bid: float,
) -> list[Flag]:
    raw: list[Flag | None] = [
        _unconfirmed_extraction(rent_roll, opex),
        _achieved_rent_unverified(rent_roll, assumptions),
        _below_agency_gate(profile, financing),
        _pre_1980_structure(profile, budget),
        _tax_reassessment_missing(opex, bid),
        _insurance_below_commercial(opex),
        _valued_on_unachieved_proforma(rent_roll, assumptions),
        _stale_rent_roll(rent_roll),
        _hbu_question(profile, assumptions),
        _contingency_below_floor(profile, budget),
    ]
    return [f for f in raw if f is not None]
