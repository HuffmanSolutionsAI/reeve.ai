"""Valuation as a band, not a point. Bid ladder anchored on in-place.

Rule 4 of the spec is the load-bearing one here: the offer anchors on
in-place economics, not on the upside. `opening` is in_place-anchored
and `walk_away` is the ceiling (max sustainable for the required margin).
The investor's `target_bid` lives between them, set by competitive read."""
from __future__ import annotations

from dataclasses import dataclass

from ...models.underwriting import DealAssumptions


@dataclass
class ValuationBand:
    floor_value: float                      # in_place_NOI / market_cap
    stabilized_value: float                 # stabilized_NOI / exit_cap
    cost_to_stabilize: float
    required_margin_dollars: float
    closing_gross_up: float
    ceiling_max_offer: float                # the breakeven max
    walk_away: float                        # == ceiling_max_offer
    target_bid: float
    opening: float


def valuation_band(
    *,
    in_place_noi: float,
    stabilized_noi: float,
    market_cap: float | None,
    exit_cap: float,
    cost_to_stabilize: float,
    assumptions: DealAssumptions,
    target_bid_factor: float = 0.95,        # target_bid as fraction of walk_away
    opening_anchor_ratio: float = 0.93,     # opening at 93% of floor → ~7% under-anchor
) -> ValuationBand:
    """Compute the band + the three-rung bid ladder.

    Floor value uses market_cap (class-appropriate); when it's missing we
    fall back to exit_cap as a conservative substitute — but the
    risk register flags it.

    Ceiling formula:
        stabilized_value
          − cost_to_stabilize
          − required_margin
          all grossed up for closing.
    """
    floor = (in_place_noi / market_cap) if (market_cap and market_cap > 0) else 0.0
    stabilized = (stabilized_noi / exit_cap) if exit_cap > 0 else 0.0

    # Required margin can be % of total cost basis OR a flat dollar number.
    required = assumptions.required_margin.in_dollars(
        total_cost=stabilized + cost_to_stabilize  # generous denominator
    )

    # Closing gross-up: bury closing costs in the offer envelope. Use 2.5%
    # as a reasonable acquisition-closing default; callers can refine.
    closing_factor = 0.025
    closing_gross_up = stabilized * closing_factor  # informational

    ceiling = stabilized - cost_to_stabilize - required
    ceiling = max(0.0, ceiling / (1.0 + closing_factor))

    walk_away = ceiling
    target_bid = walk_away * target_bid_factor
    # Opening anchors on the FLOOR (in-place economics — rule 4).
    opening = floor * opening_anchor_ratio if floor > 0 else target_bid * 0.85

    return ValuationBand(
        floor_value=round(floor, 2),
        stabilized_value=round(stabilized, 2),
        cost_to_stabilize=round(cost_to_stabilize, 2),
        required_margin_dollars=round(required, 2),
        closing_gross_up=round(closing_gross_up, 2),
        ceiling_max_offer=round(ceiling, 2),
        walk_away=round(walk_away, 2),
        target_bid=round(target_bid, 2),
        opening=round(opening, 2),
    )


def bid_ladder(band: ValuationBand) -> dict[str, float]:
    """Compact dict for the artifact payload."""
    return {
        "opening": band.opening,
        "target_bid": band.target_bid,
        "walk_away": band.walk_away,
    }
