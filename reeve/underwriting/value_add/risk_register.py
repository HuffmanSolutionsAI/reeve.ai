"""Assumption-risk register — generated, not curated.

Perturbation-based: for each material assumption-or-broker-claimed input,
re-run the ceiling computation with the input shifted by a configured
amount and record the swing in max offer. Rank by swing. The top entry
is the load-bearing assumption.

The spec's most-important behavioral commitment lives here: the agent
NAMES the load-bearing input instead of hand-waving."""
from __future__ import annotations

from dataclasses import dataclass

from ...models.underwriting import (
    DealAssumptions,
    OperatingStatement,
    PropertyProfile,
    RentRoll,
)
from .noi import stabilized_noi
from .valuation import valuation_band


@dataclass
class AssumptionRisk:
    input: str
    provenance: str           # verified | broker_claimed | assumed
    value_used: float
    perturbation_pct: float
    max_offer_low: float
    max_offer_high: float
    swing_dollars: float      # high − low
    verification_action: str | None = None


def _swing_under(
    *,
    target_rent_factor: float | None = None,
    exit_cap_delta_bps: int = 0,
    vacancy_delta: float = 0.0,
    credit_delta: float = 0.0,
    rent_roll: RentRoll,
    opex: OperatingStatement,
    assumptions: DealAssumptions,
    profile: PropertyProfile | None,
    market_cap: float | None,
    cost_to_stabilize: float,
    in_place_noi_value: float,
    bid_for_taxes: float,
) -> float:
    """Recompute the ceiling under a perturbation; return the max offer."""
    # Shallow-copy assumptions to mutate locally.
    perturbed = DealAssumptions(
        target_rents=[
            type(t)(
                condition_tier=t.condition_tier,
                unit_mix_beds=t.unit_mix_beds,
                monthly_rent=t.monthly_rent * (target_rent_factor or 1.0),
                rationale=t.rationale,
            )
            for t in assumptions.target_rents
        ],
        exit_cap=max(0.001, assumptions.exit_cap + exit_cap_delta_bps / 10000.0),
        required_margin=assumptions.required_margin,
        stabilized_vacancy=min(1.0, max(0.0, assumptions.stabilized_vacancy + vacancy_delta)),
        credit_loss=min(1.0, max(0.0, assumptions.credit_loss + credit_delta)),
        rent_growth=assumptions.rent_growth,
        lease_up_months=assumptions.lease_up_months,
        ancillary=assumptions.ancillary,
    )
    stab = stabilized_noi(rent_roll, opex, perturbed, bid_price=bid_for_taxes, profile=profile)
    band = valuation_band(
        in_place_noi=in_place_noi_value,
        stabilized_noi=stab.noi,
        market_cap=market_cap,
        exit_cap=perturbed.exit_cap,
        cost_to_stabilize=cost_to_stabilize,
        assumptions=perturbed,
    )
    return band.ceiling_max_offer


def build_risk_register(
    *,
    rent_roll: RentRoll,
    opex: OperatingStatement,
    assumptions: DealAssumptions,
    profile: PropertyProfile | None,
    market_cap: float | None,
    cost_to_stabilize: float,
    in_place_noi_value: float,
    bid_for_taxes: float,
) -> list[AssumptionRisk]:
    """Perturb each assumption and rank by max-offer swing."""
    risks: list[AssumptionRisk] = []

    def run(pct: float, **kw):
        return _swing_under(
            rent_roll=rent_roll, opex=opex, assumptions=assumptions,
            profile=profile, market_cap=market_cap,
            cost_to_stabilize=cost_to_stabilize,
            in_place_noi_value=in_place_noi_value,
            bid_for_taxes=bid_for_taxes,
            **kw,
        )

    # 1. Target rent ±10%
    if assumptions.target_rents:
        low = run(0.10, target_rent_factor=0.90)
        high = run(0.10, target_rent_factor=1.10)
        avg = sum(t.monthly_rent for t in assumptions.target_rents) / len(assumptions.target_rents)
        achieved = rent_roll.derived.achieved_renovated.mean
        risks.append(AssumptionRisk(
            input="target_rent",
            provenance=(
                "verified" if achieved is not None and abs(avg - achieved) / achieved < 0.05
                else "assumed"
            ),
            value_used=round(avg, 2),
            perturbation_pct=0.10,
            max_offer_low=round(low, 2),
            max_offer_high=round(high, 2),
            swing_dollars=round(high - low, 2),
            verification_action="Lease audit on additional renovated-occupied units to confirm achieved.",
        ))

    # 2. Exit cap ±50bps
    low = run(0.0, exit_cap_delta_bps=50)
    high = run(0.0, exit_cap_delta_bps=-50)
    risks.append(AssumptionRisk(
        input="exit_cap",
        provenance="assumed",
        value_used=assumptions.exit_cap,
        perturbation_pct=0.0,  # measured in bps for this input
        max_offer_low=round(low, 2),
        max_offer_high=round(high, 2),
        swing_dollars=round(high - low, 2),
        verification_action="Pull recent trade comps in submarket to triangulate exit cap.",
    ))

    # 3. Stabilized vacancy ±2 pts
    low = run(0.0, vacancy_delta=0.02)
    high = run(0.0, vacancy_delta=-0.02)
    risks.append(AssumptionRisk(
        input="stabilized_vacancy",
        provenance="assumed",
        value_used=assumptions.stabilized_vacancy,
        perturbation_pct=0.02,
        max_offer_low=round(low, 2),
        max_offer_high=round(high, 2),
        swing_dollars=round(high - low, 2),
        verification_action="Submarket norm; check against MSA vacancy report.",
    ))

    # 4. Credit loss ±1pt
    low = run(0.0, credit_delta=0.01)
    high = run(0.0, credit_delta=-0.01)
    risks.append(AssumptionRisk(
        input="credit_loss",
        provenance="assumed",
        value_used=assumptions.credit_loss,
        perturbation_pct=0.01,
        max_offer_low=round(low, 2),
        max_offer_high=round(high, 2),
        swing_dollars=round(high - low, 2),
        verification_action="Roll delinquency history; tenant screening standards.",
    ))

    # Rank descending by swing — the top entry is the load-bearing assumption.
    risks.sort(key=lambda r: abs(r.swing_dollars), reverse=True)
    return risks
