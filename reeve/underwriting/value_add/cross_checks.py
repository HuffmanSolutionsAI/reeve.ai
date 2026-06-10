"""Cross-check panel: cheap error-catchers, always computed."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CrossCheck:
    name: str
    value: float
    status: str          # "pass" | "warn" | "fail"
    detail: str | None = None


def _yoc_status(spread: float) -> str:
    # YoC spread vs exit cap is the negative-leverage test.
    if spread <= 0:
        return "fail"
    if spread < 0.005:    # < 50bps spread → warning territory
        return "warn"
    return "pass"


def _dscr_status(dscr: float, min_dscr: float) -> str:
    if dscr < min_dscr:
        return "fail"
    if dscr < min_dscr * 1.05:
        return "warn"
    return "pass"


def cross_check_panel(
    *,
    bid: float,
    units: int,
    in_place_noi: float,
    stabilized_noi: float,
    gross_scheduled_income_annual: float,
    cost_to_stabilize: float,
    exit_cap: float,
    perm_dscr: float | None,
    perm_min_dscr: float | None,
) -> list[CrossCheck]:
    checks: list[CrossCheck] = []

    # 1. Price per door
    ppu = bid / units if units else 0.0
    checks.append(CrossCheck(
        name="price_per_door", value=round(ppu, 2), status="pass",
        detail="Sanity check vs. comp set; no engine threshold.",
    ))

    # 2. Untrended yield on cost
    total_basis = bid + cost_to_stabilize
    yoc = (stabilized_noi / total_basis) if total_basis > 0 else 0.0
    checks.append(CrossCheck(
        name="untrended_yoc", value=round(yoc, 4), status="pass",
        detail="Stabilized NOI ÷ (price + cost-to-stabilize).",
    ))

    # 3. YoC spread vs exit cap — the negative-leverage test
    spread = yoc - exit_cap
    checks.append(CrossCheck(
        name="yoc_spread_vs_exit_cap", value=round(spread, 4),
        status=_yoc_status(spread),
        detail="Spread ≤ 0 means paying retail for wholesale work.",
    ))

    # 4. In-place cap at bid
    in_place_cap = (in_place_noi / bid) if bid > 0 else 0.0
    checks.append(CrossCheck(
        name="in_place_cap_at_bid", value=round(in_place_cap, 4), status="pass",
        detail="How much of the bid is paid out of in-place income.",
    ))

    # 5. Stabilized cap at bid
    stab_cap = (stabilized_noi / bid) if bid > 0 else 0.0
    checks.append(CrossCheck(
        name="stabilized_cap_at_bid", value=round(stab_cap, 4), status="pass",
        detail="Stabilized NOI ÷ bid. Sanity vs. market cap.",
    ))

    # 6. DSCR at perm
    if perm_dscr is not None and perm_min_dscr is not None:
        checks.append(CrossCheck(
            name="perm_dscr_at_stabilized", value=round(perm_dscr, 4),
            status=_dscr_status(perm_dscr, perm_min_dscr),
            detail=f"vs. min DSCR {perm_min_dscr:.2f}",
        ))

    # 7. GRM — gross rent multiplier
    if gross_scheduled_income_annual > 0:
        grm = bid / gross_scheduled_income_annual
        checks.append(CrossCheck(
            name="grm", value=round(grm, 2), status="pass",
            detail="Bid ÷ gross scheduled income (annual). Cross-era comp.",
        ))

    return checks
