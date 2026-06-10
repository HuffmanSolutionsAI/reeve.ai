"""Two-stage financing — bridge sized off LTC, perm sized as the lesser
of LTV-constrained and DSCR-constrained loan amounts.

The occupancy gate is honored: perm-first structures DISQUALIFY when
current physical occupancy is below the gate threshold (e.g. Freddie SBL
90/90), forcing a bridge-to-perm path. Callers receive both the chosen
loan amount and the disqualification flag so the UI/risk register can
surface it."""
from __future__ import annotations

from dataclasses import dataclass

from ...models.underwriting import FinancingScenario


@dataclass
class FinancingSizing:
    label: str

    # Bridge phase
    bridge_basis: float                # price + reno (the LTC basis)
    bridge_proceeds: float             # ltc × basis
    bridge_equity_in: float            # basis − bridge_proceeds + closing
    bridge_io_monthly: float
    bridge_annual_interest: float

    # Perm sizing
    debt_constant_annual: float        # annual P&I per $1 of perm loan
    perm_by_ltv: float
    perm_by_dscr: float
    perm_loan: float                   # min(perm_by_ltv, perm_by_dscr)
    perm_annual_ds: float
    perm_dscr_at_stabilized: float

    # Refi event
    refi_costs: float
    refi_proceeds_net: float            # perm_loan − refi_costs
    equity_recapture: float            # refi_proceeds_net − bridge balance to pay off
    residual_equity: float              # equity in − recapture
    stabilized_cash_on_cash: float

    # Gating
    perm_first_qualifies: bool          # current_occupancy ≥ perm.occupancy_gate
    occupancy_gate_pct: float
    structure: str                      # "bridge_to_perm" | "perm_first" | "all_cash" | "no_perm"


def size_financing(
    *,
    bid_price: float,
    cost_to_stabilize_total: float,
    stabilized_noi: float,
    stabilized_value: float,
    in_place_physical_occupancy: float,
    financing: FinancingScenario,
    total_equity_in: float | None = None,
) -> FinancingSizing:
    bridge = financing.bridge
    perm = financing.perm

    # Bridge sizing
    if bridge is not None:
        basis = bid_price + cost_to_stabilize_total
        proceeds = basis * bridge.ltc
        bridge_equity = max(0.0, basis - proceeds)
        bridge_monthly_int = bridge.monthly_io_payment(proceeds)
        bridge_annual_int = bridge_monthly_int * 12.0
    else:
        basis = bid_price + cost_to_stabilize_total
        proceeds = 0.0
        bridge_equity = basis
        bridge_monthly_int = 0.0
        bridge_annual_int = 0.0

    # Perm sizing (lesser-of)
    if perm is not None and stabilized_noi > 0:
        annual_constant = perm.annual_debt_constant()
        perm_by_ltv = perm.max_ltv * stabilized_value
        perm_by_dscr = stabilized_noi / (perm.min_dscr * annual_constant)
        perm_loan = min(perm_by_ltv, perm_by_dscr)
        perm_annual_ds = perm_loan * annual_constant
        perm_dscr = stabilized_noi / perm_annual_ds if perm_annual_ds > 0 else float("inf")
        refi_costs = perm_loan * perm.refi_costs_pct
        gate_pct = perm.occupancy_gate.occupancy
        perm_first_ok = perm.occupancy_gate.met_by(in_place_physical_occupancy)
    else:
        annual_constant = 0.0
        perm_by_ltv = perm_by_dscr = perm_loan = 0.0
        perm_annual_ds = 0.0
        perm_dscr = 0.0
        refi_costs = 0.0
        gate_pct = 0.0
        perm_first_ok = False

    # Equity flow
    refi_proceeds_net = max(0.0, perm_loan - refi_costs)
    # The bridge loan gets paid off out of refi proceeds; recapture is what's
    # left over (capped at 0 — refi can't go negative, equity stays in).
    equity_recapture = max(0.0, refi_proceeds_net - proceeds)

    equity_in = total_equity_in if total_equity_in is not None else bridge_equity
    residual_equity = max(0.0, equity_in - equity_recapture)
    if residual_equity > 0 and stabilized_noi - perm_annual_ds > 0:
        coc = (stabilized_noi - perm_annual_ds) / residual_equity
    else:
        coc = 0.0

    # Structure determination
    if perm is None and bridge is None:
        structure = "all_cash"
    elif perm is None:
        structure = "bridge_only"
    elif bridge is None and perm_first_ok:
        structure = "perm_first"
    elif bridge is None and not perm_first_ok:
        # Caller said perm-first but occupancy gate disqualifies.
        structure = "no_perm"  # disqualified
    else:
        # bridge present and perm present → bridge-to-perm
        structure = "bridge_to_perm"

    return FinancingSizing(
        label=financing.label,
        bridge_basis=round(basis, 2),
        bridge_proceeds=round(proceeds, 2),
        bridge_equity_in=round(bridge_equity, 2),
        bridge_io_monthly=round(bridge_monthly_int, 2),
        bridge_annual_interest=round(bridge_annual_int, 2),
        debt_constant_annual=round(annual_constant, 6),
        perm_by_ltv=round(perm_by_ltv, 2),
        perm_by_dscr=round(perm_by_dscr, 2),
        perm_loan=round(perm_loan, 2),
        perm_annual_ds=round(perm_annual_ds, 2),
        perm_dscr_at_stabilized=round(perm_dscr, 4),
        refi_costs=round(refi_costs, 2),
        refi_proceeds_net=round(refi_proceeds_net, 2),
        equity_recapture=round(equity_recapture, 2),
        residual_equity=round(residual_equity, 2),
        stabilized_cash_on_cash=round(coc, 4),
        perm_first_qualifies=perm_first_ok,
        occupancy_gate_pct=gate_pct,
        structure=structure,
    )
