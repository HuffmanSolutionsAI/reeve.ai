"""Three NOI states + the broker-pro-forma diff.

The rules (§5 of the data-model doc), made arithmetic:

  1. NOI is BEFORE CapEx, reserves, and debt service. Reserves are
     reported separately; debt service is sized in `financing.py`.
  2. NEVER model OpEx as % of EGI at low occupancy. In-place uses
     T-12 DOLLARS with two corrections — taxes substituted with
     reassessment-at-bid, insurance substituted with the commercial
     quote — and nothing else scales with occupancy.
  3. Reassess taxes at the candidate bid price. The bid flows in as a
     parameter so the sensitivity grid can re-derive per cell.
  4. Insurance: commercial quote if available, else the current annual.
  5. Ancillary income belongs only to state 3 — never to in-place or to
     the stabilized-base used for the offer.
  6. The broker pro-forma is stored verbatim and rebuilt line-for-line
     here; it never feeds another state's math."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ...models.underwriting import (
    DealAssumptions,
    OperatingStatement,
    OpExCategory,
    PropertyProfile,
    RentRoll,
)


NOIState = Literal["in_place", "stabilized", "stabilized_plus_ancillary"]


@dataclass
class NOIBreakdown:
    """A complete decomposition of one NOI state. All values annual.

    `opex_lines` is the per-category dollar map that fed the OpEx total.
    Stored on the result so the UI can show a line-by-line panel without
    re-derivation."""
    state: NOIState
    gross_potential_income: float
    vacancy_loss: float
    credit_loss: float
    concession_loss: float
    other_income: float            # ancillary only in state 3
    effective_gross_income: float
    opex_lines: dict[str, float] = field(default_factory=dict)
    opex_total: float = 0.0
    noi: float = 0.0               # EGI − opex_total. NOT including reserves or DS.
    reserves: float = 0.0          # below-the-line; carried for DSCR


# ---- internal helpers ---------------------------------------------------
def _opex_dollar_map(
    opex: OperatingStatement,
    *,
    bid_price: float,
    exclude_for_substitution: bool = True,
) -> dict[str, float]:
    """Return a category-keyed dollar map drawn from the T-12 dollars.

    Two substitutions apply when `exclude_for_substitution` is True:
      - `taxes` → reassessment-at-bid (TaxRecord.reassessed_at(bid_price)
        if computable, else the static estimate, else the T-12 value).
      - `insurance` → commercial quote when present, else current annual,
        else the T-12 value.
    """
    out: dict[str, float] = {}
    for line in opex.lines:
        cat = line.category if isinstance(line.category, str) else line.category.value
        if exclude_for_substitution and cat in {OpExCategory.TAXES.value, OpExCategory.INSURANCE.value}:
            continue
        out[cat] = out.get(cat, 0.0) + line.annual.value

    # Tax substitution
    tax_at_bid = opex.tax.reassessed_at(bid_price)
    if tax_at_bid is None:
        # Fall back to the T-12 tax line if reassessment is unavailable.
        tax_at_bid = opex.annual_for(OpExCategory.TAXES)
    out[OpExCategory.TAXES.value] = round(tax_at_bid, 2)

    # Insurance substitution
    if opex.insurance.commercial_quote is not None:
        ins = opex.insurance.commercial_quote.value
    elif opex.insurance.current_annual is not None:
        ins = opex.insurance.current_annual.value
    else:
        ins = opex.annual_for(OpExCategory.INSURANCE)
    out[OpExCategory.INSURANCE.value] = round(ins, 2)

    return out


def _reserves_annual(opex: OperatingStatement, units_total: int) -> float:
    return float(opex.reserves_per_door) * units_total


# ---- the three states --------------------------------------------------
def in_place_noi(
    rent_roll: RentRoll, opex: OperatingStatement, *, bid_price: float,
) -> NOIBreakdown:
    """State 1: as-is income, T-12 dollar expenses with tax/insurance fixes.

    GPI uses effective contract rent (in_place − concessions) on OCCUPIED
    units only. Vacancy and credit loss are observed, not assumed:
      - vacancy_loss is structural in the GPI base (vacant units
        contribute zero, by construction).
      - credit_loss = delinquency totals from the roll, monthly × 12.

    Fixed costs (taxes, insurance, mgmt floor, payroll, etc.) are not
    scaled with occupancy — that's the whole point of switching off the
    % of EGI model."""
    occupied = [r for r in rent_roll.leases if r.occupied]
    gpi_monthly = sum(r.effective_in_place_monthly() for r in occupied)
    gpi_annual = gpi_monthly * 12.0

    # Concessions: amortized monthly amounts are already netted inside
    # effective_in_place_monthly, but report the gross loss for the panel.
    concession_loss_annual = sum(r.concessions for r in occupied) * 12.0

    # Delinquency: roll values are balances; we treat them as the annual
    # credit-loss observed.
    credit_loss_annual = sum(r.delinquent_balance for r in rent_roll.leases)

    # Vacancy: implicit (vacant units contribute 0 to GPI). For the panel
    # we surface the "would-be" loss against in-place avg.
    units_total = rent_roll.derived.units_total or len(rent_roll.leases)
    occupied_n = len(occupied)
    if occupied_n and occupied_n < units_total:
        in_place_avg = gpi_monthly / occupied_n
        vacancy_loss_annual = in_place_avg * (units_total - occupied_n) * 12.0
    else:
        vacancy_loss_annual = 0.0

    egi = gpi_annual - credit_loss_annual

    opex_map = _opex_dollar_map(opex, bid_price=bid_price)
    opex_total = sum(opex_map.values())

    return NOIBreakdown(
        state="in_place",
        gross_potential_income=round(gpi_annual, 2),
        vacancy_loss=round(vacancy_loss_annual, 2),
        credit_loss=round(credit_loss_annual, 2),
        concession_loss=round(concession_loss_annual, 2),
        other_income=0.0,
        effective_gross_income=round(egi, 2),
        opex_lines={k: round(v, 2) for k, v in opex_map.items()},
        opex_total=round(opex_total, 2),
        noi=round(egi - opex_total, 2),
        reserves=round(_reserves_annual(opex, units_total), 2),
    )


def _stabilized_gpi_annual(
    rent_roll: RentRoll,
    assumptions: DealAssumptions,
    profile: PropertyProfile | None,
) -> float:
    """GPI at stabilized state: target rent × every unit. Per-tier when a
    tier-keyed target exists; otherwise a single weighted-average target
    applied to every unit."""
    by_label_tier = {r.unit_label: r.condition_tier for r in rent_roll.leases}
    total_monthly = 0.0
    if assumptions.target_rents:
        # Try per-tier first; fall back to bedroom-keyed; final fallback to first target.
        for row in rent_roll.leases:
            rent = assumptions.target_rent_for(tier=row.condition_tier)
            if rent is None and profile is not None and profile.unit_mix:
                # No tier mapping; use any first mix entry's bedroom-keyed lookup
                rent = assumptions.target_rent_for(beds=profile.unit_mix[0].beds)
            if rent is None:
                rent = assumptions.target_rents[0].monthly_rent
            total_monthly += rent
    return total_monthly * 12.0


def stabilized_noi(
    rent_roll: RentRoll,
    opex: OperatingStatement,
    assumptions: DealAssumptions,
    *,
    bid_price: float,
    profile: PropertyProfile | None = None,
) -> NOIBreakdown:
    """State 2: stabilized base. Income at target rents × all units, with
    assumed vacancy + credit-loss; OpEx in T-12 dollars (with the two
    substitutions); variable lines (turns, mgmt %) scaled to stabilized
    occupancy rather than current depressed occupancy."""
    gpi = _stabilized_gpi_annual(rent_roll, assumptions, profile)
    vacancy = gpi * assumptions.stabilized_vacancy
    credit = gpi * assumptions.credit_loss
    egi = gpi - vacancy - credit

    units_total = rent_roll.derived.units_total or len(rent_roll.leases)
    opex_map = _opex_dollar_map(opex, bid_price=bid_price)

    # Variable line scaling: management fee is the obvious one — usually
    # quoted as % of EGI by the manager, so we replace the T-12 dollar
    # figure with `mgmt_pct * stabilized EGI` when we can infer the rate.
    # If the T-12 mgmt fee is plausibly a fixed dollar, leave it alone.
    in_place_egi_monthly = sum(
        r.effective_in_place_monthly() for r in rent_roll.leases if r.occupied
    ) * 12.0
    if in_place_egi_monthly > 0 and opex_map.get(OpExCategory.MGMT_FEE.value, 0) > 0:
        implied_rate = opex_map[OpExCategory.MGMT_FEE.value] / in_place_egi_monthly
        if 0.03 <= implied_rate <= 0.12:
            opex_map[OpExCategory.MGMT_FEE.value] = round(implied_rate * egi, 2)

    # Turns scale with unit count + turnover, not occupancy. Leave alone.
    opex_total = sum(opex_map.values())

    return NOIBreakdown(
        state="stabilized",
        gross_potential_income=round(gpi, 2),
        vacancy_loss=round(vacancy, 2),
        credit_loss=round(credit, 2),
        concession_loss=0.0,             # stabilized assumes no leases-with-concession
        other_income=0.0,
        effective_gross_income=round(egi, 2),
        opex_lines={k: round(v, 2) for k, v in opex_map.items()},
        opex_total=round(opex_total, 2),
        noi=round(egi - opex_total, 2),
        reserves=round(_reserves_annual(opex, units_total), 2),
    )


def stabilized_plus_ancillary_noi(
    base: NOIBreakdown, assumptions: DealAssumptions,
) -> NOIBreakdown:
    """State 3: base stabilized + ancillary income (and any opex it adds)."""
    add_income = assumptions.total_ancillary_annual
    add_opex = assumptions.total_ancillary_opex_annual
    new_egi = base.effective_gross_income + add_income
    new_lines = dict(base.opex_lines)
    if add_opex > 0:
        new_lines["ancillary_opex"] = round(add_opex, 2)
    new_total = sum(new_lines.values())
    return NOIBreakdown(
        state="stabilized_plus_ancillary",
        gross_potential_income=base.gross_potential_income,
        vacancy_loss=base.vacancy_loss,
        credit_loss=base.credit_loss,
        concession_loss=0.0,
        other_income=round(add_income, 2),
        effective_gross_income=round(new_egi, 2),
        opex_lines={k: round(v, 2) for k, v in new_lines.items()},
        opex_total=round(new_total, 2),
        noi=round(new_egi - new_total, 2),
        reserves=base.reserves,
    )


# ---- broker pro-forma diff ---------------------------------------------
@dataclass
class BrokerDiffLine:
    line: str
    broker: float | None
    engine: float | None
    delta: float | None    # broker − engine; positive = broker is rosier


def broker_proforma_diff(
    broker, engine_state: NOIBreakdown,
) -> list[BrokerDiffLine]:
    """Compare the OM's claimed NOI/rents against the engine's same-state
    rebuild. Reported separately; never feeds math."""
    out: list[BrokerDiffLine] = []
    if broker is None:
        return out
    if broker.asking_noi is not None:
        out.append(BrokerDiffLine(
            line="noi",
            broker=broker.asking_noi,
            engine=engine_state.noi,
            delta=round(broker.asking_noi - engine_state.noi, 2),
        ))
    if broker.opex_assumption_annual is not None:
        out.append(BrokerDiffLine(
            line="opex_total",
            broker=broker.opex_assumption_annual,
            engine=engine_state.opex_total,
            delta=round(broker.opex_assumption_annual - engine_state.opex_total, 2),
        ))
    return out
