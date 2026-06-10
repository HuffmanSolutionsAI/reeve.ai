"""Cost-to-stabilize — the term most often silently omitted is `net carry`,
so it's a named line."""
from __future__ import annotations

from dataclasses import dataclass

from ...models.underwriting import (
    DealAssumptions,
    FinancingScenario,
    RenovationBudget,
)


@dataclass
class StabilizationCosts:
    renovation: float
    make_ready: float            # rent-ready turn cost
    lease_up_carry: float        # ancillary lease-up costs (marketing, etc.)
    net_carry: float             # bridge interest minus partial in-place NOI
    closing_acquisition: float
    closing_refi: float
    total: float


def cost_to_stabilize(
    *,
    bid_price: float,
    budget: RenovationBudget,
    financing: FinancingScenario,
    assumptions: DealAssumptions,
    in_place_noi_annual: float,
) -> StabilizationCosts:
    """Sum of every dollar between today and the stabilized refi.

    Net carry: over the lease-up window, the bridge accrues interest while
    in-place income covers only a fraction of it. We approximate the
    average bridge balance as full balance for the IO period (since IO
    means no principal reduction); the in-place income earned during the
    period offsets it. The result is monthly accruals summed across the
    lease-up window."""
    renovation = budget.total
    rent_ready_units = sum(
        bt.units_count for bt in budget.tiers
        if (bt.condition_tier == "rent_ready" or (
            hasattr(bt.condition_tier, "value") and bt.condition_tier.value == "rent_ready"
        ))
    )
    # Make-ready is the rent-ready turn cost; if a tier line already
    # included it, the caller leaves `make_ready_per_unit` at 0.
    make_ready = budget.make_ready_per_unit * rent_ready_units

    # Lease-up carry — marketing, turn velocity. Crude proxy: 0.5 month of
    # in-place NOI as a non-rent expense bucket. (The schema lets callers
    # override by adding a marketing OpEx line in the operating statement
    # at stabilization; here we surface it as a named line.)
    lease_up_carry = max(0.0, in_place_noi_annual * (0.5 / 12.0))

    # Net carry.
    months = assumptions.lease_up_months
    if financing.bridge is not None and months > 0:
        # Loan balance during reno: price + reno × LTC (the bridge's basis).
        bridge_basis = (bid_price + renovation) * financing.bridge.ltc
        monthly_interest = financing.bridge.monthly_io_payment(bridge_basis)
        gross_carry = monthly_interest * months
        partial_in_place = in_place_noi_annual * (months / 12.0)
        net_carry = max(0.0, gross_carry - partial_in_place)
    else:
        # All-cash or perm-first: no bridge interest accrual.
        net_carry = 0.0

    closing_acq = bid_price * budget.closing_costs_pct
    # Refi closing — only on bridge-to-perm.
    if financing.perm is not None and financing.bridge is not None:
        # Estimate as % of expected refi proceeds (use perm.max_ltv × bid
        # as a placeholder; the real number lives in financing sizing).
        closing_refi = (bid_price + renovation) * 0.005  # ~50bps placeholder
    else:
        closing_refi = 0.0

    total = (
        renovation + make_ready + lease_up_carry + net_carry
        + closing_acq + closing_refi
    )
    return StabilizationCosts(
        renovation=round(renovation, 2),
        make_ready=round(make_ready, 2),
        lease_up_carry=round(lease_up_carry, 2),
        net_carry=round(net_carry, 2),
        closing_acquisition=round(closing_acq, 2),
        closing_refi=round(closing_refi, 2),
        total=round(total, 2),
    )
