"""Machine validation for staged documents (§8 of the data-model doc).

Run at ingest time; results are stored on the staged record so the human
confirmation screen shows the extractor's work being checked, not a
re-keyed document. A failed check does NOT block ingest — it blocks
CONFIDENCE (the `unconfirmed_extraction` flag stays up until a human
confirms, and the confirmation UI renders every failure loudly)."""
from __future__ import annotations

from datetime import date

from ..models.underwriting import (
    OperatingStatement,
    RentRoll,
    RentRollValidation,
    ValidationCheck,
)


def validate_rent_roll(
    rr: RentRoll,
    *,
    claimed_unit_count: int | None = None,
    claimed_occupancy: float | None = None,
    stated_monthly_total: float | None = None,
) -> RentRollValidation:
    """The four machine checks from the spec, plus tier-consistency.

    The `claimed_*` parameters are what the source document SAYS about
    itself (its own totals row, its own occupancy line); the checks
    compare the extracted rows against those claims and catch the classic
    extraction failures: skipped page (row count short), transposed
    column (sums wrong), garbled dates."""
    checks: list[ValidationCheck] = []

    # 1. Row count vs claimed unit count
    rows = len(rr.leases)
    if claimed_unit_count is not None:
        checks.append(ValidationCheck(
            name="row_count_matches_claimed_units",
            passed=rows == claimed_unit_count,
            detail=f"extracted {rows} rows; document claims {claimed_unit_count} units",
        ))
    else:
        checks.append(ValidationCheck(
            name="row_count_matches_claimed_units",
            passed=True,
            detail=f"extracted {rows} rows; no claimed count to compare (skipped)",
        ))

    # 2. Occupancy consistency
    occupied = sum(1 for r in rr.leases if r.occupied)
    derived_occ = occupied / rows if rows else 0.0
    if claimed_occupancy is not None:
        delta = abs(derived_occ - claimed_occupancy)
        checks.append(ValidationCheck(
            name="occupancy_consistent_with_claim",
            passed=delta <= 0.02,
            detail=f"rows imply {derived_occ:.1%}; document claims {claimed_occupancy:.1%}",
        ))
    else:
        checks.append(ValidationCheck(
            name="occupancy_consistent_with_claim",
            passed=True,
            detail=f"rows imply {derived_occ:.1%}; no claimed occupancy to compare (skipped)",
        ))

    # 3. Rent column sums vs stated total
    rent_sum = sum(
        r.in_place_rent.value for r in rr.leases
        if r.occupied and r.in_place_rent is not None
    )
    if stated_monthly_total is not None:
        delta = abs(rent_sum - stated_monthly_total)
        tolerance = max(1.0, stated_monthly_total * 0.005)  # 0.5% or $1
        checks.append(ValidationCheck(
            name="rent_sum_matches_stated_total",
            passed=delta <= tolerance,
            detail=f"rows sum to ${rent_sum:,.2f}; document states ${stated_monthly_total:,.2f}",
        ))
    else:
        checks.append(ValidationCheck(
            name="rent_sum_matches_stated_total",
            passed=True,
            detail=f"rows sum to ${rent_sum:,.2f}; no stated total to compare (skipped)",
        ))

    # 4. Dates parse + lease_end ≥ lease_start
    bad_dates: list[str] = []
    for r in rr.leases:
        try:
            d_start = date.fromisoformat(r.lease_start) if r.lease_start else None
            d_end = date.fromisoformat(r.lease_end) if r.lease_end else None
            if d_start and d_end and d_end < d_start:
                bad_dates.append(f"{r.unit_label}: end before start")
        except ValueError:
            bad_dates.append(f"{r.unit_label}: unparseable date")
    checks.append(ValidationCheck(
        name="lease_dates_parse",
        passed=not bad_dates,
        detail="; ".join(bad_dates) if bad_dates else "all dates parse",
    ))

    # 5. Occupied rows carry an in-place rent
    missing_rent = [
        r.unit_label for r in rr.leases
        if r.occupied and r.in_place_rent is None
    ]
    checks.append(ValidationCheck(
        name="occupied_rows_have_rent",
        passed=not missing_rent,
        detail=(
            f"occupied without in_place_rent: {', '.join(missing_rent)}"
            if missing_rent else "every occupied row has a rent"
        ),
    ))

    return RentRollValidation(checks=checks)


def validate_operating_statement(
    opex: OperatingStatement,
    *,
    stated_annual_total: float | None = None,
) -> RentRollValidation:
    """T-12 checks: line sums vs stated total, full-year period, monthly
    arrays consistent with annual figures."""
    checks: list[ValidationCheck] = []

    # 1. Period is actually trailing-12
    checks.append(ValidationCheck(
        name="period_is_full_year",
        passed=opex.period.is_full_year(),
        detail=f"{opex.period.start} → {opex.period.end}",
    ))

    # 2. Line sums vs the document's stated annual total
    lines_total = sum(line.annual.value for line in opex.lines)
    if stated_annual_total is not None:
        tolerance = max(1.0, stated_annual_total * 0.005)
        checks.append(ValidationCheck(
            name="line_sum_matches_stated_total",
            passed=abs(lines_total - stated_annual_total) <= tolerance,
            detail=f"lines sum to ${lines_total:,.2f}; document states ${stated_annual_total:,.2f}",
        ))
    else:
        checks.append(ValidationCheck(
            name="line_sum_matches_stated_total",
            passed=True,
            detail=f"lines sum to ${lines_total:,.2f}; no stated total to compare (skipped)",
        ))

    # 3. Monthly detail (when present) reconciles to the annual figure
    bad_monthly: list[str] = []
    for line in opex.lines:
        if line.monthly:
            if len(line.monthly) != 12:
                bad_monthly.append(f"{line.category}: {len(line.monthly)} months")
                continue
            m_sum = sum(line.monthly)
            if abs(m_sum - line.annual.value) > max(1.0, line.annual.value * 0.01):
                bad_monthly.append(
                    f"{line.category}: monthly sums ${m_sum:,.0f} vs annual ${line.annual.value:,.0f}"
                )
    checks.append(ValidationCheck(
        name="monthly_detail_reconciles",
        passed=not bad_monthly,
        detail="; ".join(bad_monthly) if bad_monthly else "monthly detail reconciles (or absent)",
    ))

    # 4. No negative expense lines (a transposed credit is a classic
    # extraction artifact).
    negative = [
        str(line.category) for line in opex.lines if line.annual.value < 0
    ]
    checks.append(ValidationCheck(
        name="no_negative_expense_lines",
        passed=not negative,
        detail=f"negative lines: {', '.join(negative)}" if negative else "all lines non-negative",
    ))

    return RentRollValidation(checks=checks)
