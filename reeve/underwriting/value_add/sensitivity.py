"""Sensitivity grid: target rent × exit cap.

For each cell:
  - rebuild stabilized NOI using the perturbed target rent;
  - re-derive taxes at the recomputed bid using millage × bid;
  - divide by perturbed exit cap;
  - apply the ceiling formula (stabilized − cost − margin).

The output's headline is the SWING (max − min) across cells, not the
center value. The spec demands that explicitly: '...the agent should
report how much the answer swings, not just a number.'"""
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
class SensitivityCell:
    target_rent_delta_pct: float
    exit_cap_delta_bps: int
    target_rent_used_avg: float
    exit_cap_used: float
    stabilized_noi: float
    max_offer: float


def sensitivity_grid(
    *,
    rent_roll: RentRoll,
    opex: OperatingStatement,
    assumptions: DealAssumptions,
    profile: PropertyProfile | None,
    market_cap: float | None,
    cost_to_stabilize: float,
    in_place_noi: float,
    bid_for_taxes: float,
    rent_deltas_pct: tuple[float, ...] = (-0.10, -0.05, 0.0, 0.05, 0.10),
    cap_deltas_bps: tuple[int, ...] = (-100, -50, 0, 50, 100),
) -> tuple[list[SensitivityCell], float]:
    """Returns (cells, swing). Swing is max_offer.max − max_offer.min."""
    cells: list[SensitivityCell] = []
    for d_rent in rent_deltas_pct:
        # Build a perturbed assumptions copy with each target rent shifted.
        perturbed_targets = [
            type(t)(
                condition_tier=t.condition_tier,
                unit_mix_beds=t.unit_mix_beds,
                monthly_rent=max(0.0, t.monthly_rent * (1.0 + d_rent)),
                rationale=t.rationale,
            )
            for t in assumptions.target_rents
        ]
        perturbed = type(assumptions)(
            target_rents=perturbed_targets,
            exit_cap=assumptions.exit_cap,
            required_margin=assumptions.required_margin,
            stabilized_vacancy=assumptions.stabilized_vacancy,
            credit_loss=assumptions.credit_loss,
            rent_growth=assumptions.rent_growth,
            lease_up_months=assumptions.lease_up_months,
            ancillary=assumptions.ancillary,
        )
        stab = stabilized_noi(rent_roll, opex, perturbed, bid_price=bid_for_taxes, profile=profile)
        avg_target = (
            sum(t.monthly_rent for t in perturbed_targets) / len(perturbed_targets)
            if perturbed_targets else 0.0
        )
        for d_cap in cap_deltas_bps:
            exit_cap = max(0.001, assumptions.exit_cap + d_cap / 10000.0)
            perturbed.exit_cap = exit_cap
            band = valuation_band(
                in_place_noi=in_place_noi,
                stabilized_noi=stab.noi,
                market_cap=market_cap,
                exit_cap=exit_cap,
                cost_to_stabilize=cost_to_stabilize,
                assumptions=perturbed,
            )
            cells.append(SensitivityCell(
                target_rent_delta_pct=d_rent,
                exit_cap_delta_bps=d_cap,
                target_rent_used_avg=round(avg_target, 2),
                exit_cap_used=round(exit_cap, 4),
                stabilized_noi=round(stab.noi, 2),
                max_offer=round(band.ceiling_max_offer, 2),
            ))

    offers = [c.max_offer for c in cells]
    swing = round(max(offers) - min(offers), 2) if offers else 0.0
    return cells, swing
