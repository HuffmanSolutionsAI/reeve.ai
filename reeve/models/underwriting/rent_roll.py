"""RentRoll — staged collection (rent_rolls).

A lease-by-lease snapshot. Lives in its own Mongo collection (not embedded
on Deal) because:
  - It's large and ingested from files (PDF/XLSX/CSV → extraction → review).
  - It carries its own confirmation lifecycle (`human_confirmed` gate).
  - It is superseded by re-ingests the same way artifacts are versioned.

Critical distinction encoded in `LeaseRow`:
  - `in_place_rent`  — contract rent on the current lease (real money).
  - `achieved_rent`  — populated ONLY when condition_tier == renovated
                       AND occupied. The signed lease at the post-reno
                       standard. The load-bearing number for the
                       stabilized rent assumption.
  - `asking_rent`    — what the listing/OM asks. Carried so the gap to
                       achieved is computable; NEVER feeds NOI math.

`RentRoll.derived` is recomputed at confirm time and stored on the
envelope. `achieved_renovated.n` matters: two observations is anecdote,
twelve is evidence; the risk register reads it."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..base import BaseDoc
from .provenance import Provenance, Sourced


class ConditionTier(str, Enum):
    RENOVATED = "renovated"
    RENT_READY = "rent_ready"
    DOWN = "down"


class IngestFormat(str, Enum):
    PDF = "pdf"
    XLSX = "xlsx"
    CSV = "csv"
    MANUAL = "manual"


class RentRollSource(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    file_name: str | None = None
    format: IngestFormat = IngestFormat.MANUAL
    ingested_at: str | None = None
    extraction_method: str | None = None  # "llm-claude", "tabula", "hand-entered"


class ValidationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    passed: bool
    detail: str | None = None


class RentRollValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checks: list[ValidationCheck] = Field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)


class LeaseRow(BaseModel):
    """One unit's row in the rent roll."""
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    unit_label: str
    condition_tier: ConditionTier
    occupied: bool

    # ---- income fields — provenance matters --------------------------
    # In-place rent: contract rent on the active lease. None for vacant.
    in_place_rent: Sourced[float] | None = None
    # Achieved rent: load-bearing. Only valid on renovated + occupied.
    achieved_rent: Sourced[float] | None = None
    # Asking rent: broker-claimed by definition. Never feeds NOI math.
    asking_rent: Sourced[float] | None = None

    # ---- lease term + adjustments ------------------------------------
    lease_start: str | None = None
    lease_end: str | None = None
    concessions: float = 0.0          # amortized monthly concession amount
    delinquent_balance: float = 0.0
    notes: str | None = None

    @model_validator(mode="after")
    def _achieved_only_on_renovated_occupied(self) -> "LeaseRow":
        # achieved_rent has a specific meaning. If the data isn't structurally
        # achieved-renovated, the field must be null.
        if self.achieved_rent is not None and not (
            self.condition_tier == ConditionTier.RENOVATED.value
            or self.condition_tier == ConditionTier.RENOVATED
        ):
            raise ValueError("achieved_rent is only valid when condition_tier=renovated")
        if self.achieved_rent is not None and not self.occupied:
            raise ValueError("achieved_rent is only valid on occupied units (signed lease)")
        return self

    def effective_in_place_monthly(self) -> float:
        """Contract rent minus amortized concessions. Used in NOI math.
        Returns 0 for vacant units."""
        if not self.occupied or self.in_place_rent is None:
            return 0.0
        return max(0.0, self.in_place_rent.value - self.concessions)


class AchievedRenovatedStats(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int = 0
    mean: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None


class RentRollDerived(BaseModel):
    """Computed at confirm time. Stored so downstream consumers don't
    recompute. Recomputed via `recompute()` after edits."""
    model_config = ConfigDict(extra="forbid")

    units_total: int = 0
    occupied_count: int = 0
    physical_occupancy: float = 0.0       # occupied / total
    gross_scheduled_rent_monthly: float = 0.0       # sum of in_place on occupied
    economic_occupancy: float | None = None         # delinquency-aware
    avg_in_place_by_tier: dict[str, float] = Field(default_factory=dict)
    achieved_renovated: AchievedRenovatedStats = Field(default_factory=AchievedRenovatedStats)


class RentRoll(BaseDoc):
    """Staged document. Mongo collection `rent_rolls`."""

    deal_id: str
    investor_id: str                                 # query scoping
    as_of: str                                       # ISO date — staleness driver
    source: RentRollSource = Field(default_factory=RentRollSource)
    leases: list[LeaseRow] = Field(default_factory=list)
    validation: RentRollValidation = Field(default_factory=RentRollValidation)
    human_confirmed: bool = False
    confirmed_by: str | None = None                  # investor id of confirmer
    confirmed_at: str | None = None
    supersedes: str | None = None                    # prior rent_roll _id
    derived: RentRollDerived = Field(default_factory=RentRollDerived)


def recompute_derived(rr: RentRoll) -> RentRollDerived:
    """Compute the envelope's derived stats from the lease rows.

    Pure: returns a fresh RentRollDerived; the caller writes it back."""
    leases = rr.leases
    total = len(leases)
    occupied = [r for r in leases if r.occupied]
    occ_count = len(occupied)
    gpi_monthly = sum(r.effective_in_place_monthly() for r in occupied)

    # Economic occupancy = (GPI − delinquency) / (target potential at current
    # in-place rents on every unit including vacancies). We use occupied-unit
    # avg for vacant units' potential, since asking_rent is broker-claimed.
    if occupied and total:
        in_place_avg = (
            sum(r.in_place_rent.value for r in occupied if r.in_place_rent is not None)
            / max(1, sum(1 for r in occupied if r.in_place_rent is not None))
        )
        potential = in_place_avg * total
        delinquency = sum(r.delinquent_balance for r in leases)
        econ_occ = max(0.0, (gpi_monthly - delinquency)) / potential if potential else 0.0
    else:
        econ_occ = 0.0

    # By tier averages (in-place, occupied).
    by_tier: dict[str, list[float]] = {}
    for r in occupied:
        if r.in_place_rent is not None:
            by_tier.setdefault(
                r.condition_tier
                if isinstance(r.condition_tier, str)
                else r.condition_tier.value,
                [],
            ).append(r.in_place_rent.value)
    avg_by_tier = {k: round(sum(v) / len(v), 2) for k, v in by_tier.items() if v}

    # Achieved renovated stats — the load-bearing observation set.
    achieved = [
        r.achieved_rent.value for r in leases
        if r.achieved_rent is not None
    ]
    if achieved:
        sorted_ach = sorted(achieved)
        stats = AchievedRenovatedStats(
            n=len(achieved),
            mean=round(sum(achieved) / len(achieved), 2),
            median=sorted_ach[len(sorted_ach) // 2],
            min=min(achieved),
            max=max(achieved),
        )
    else:
        stats = AchievedRenovatedStats()

    return RentRollDerived(
        units_total=total,
        occupied_count=occ_count,
        physical_occupancy=round(occ_count / total, 4) if total else 0.0,
        gross_scheduled_rent_monthly=round(gpi_monthly, 2),
        economic_occupancy=round(econ_occ, 4) if econ_occ else None,
        avg_in_place_by_tier=avg_by_tier,
        achieved_renovated=stats,
    )
