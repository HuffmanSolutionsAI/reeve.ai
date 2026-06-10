"""RenovationBudget — scope + costs to the target standard.

Embedded on Deal. Three structural calls the spec demands:
  - Per-tier cost (down units cost full reno; rent-ready only make-ready).
  - Explicit systems lines for old structures (panels, plumbing, HVAC),
    not a blended per-unit number.
  - Pre-1980 abatement allowance + an age-scaled contingency floor.

The engine refuses a budget that violates the contingency floor."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Sourced
from .rent_roll import ConditionTier


# Suggested contingency floor (the engine uses these).
CONTINGENCY_FLOOR_BASE = 0.10
CONTINGENCY_BUMP_PRE_1980 = 0.05
CONTINGENCY_BUMP_UNTESTED_SYSTEMS = 0.05


class SystemItem(str, Enum):
    ELECTRICAL_PANEL = "electrical_panel"
    PLUMBING_SUPPLY = "plumbing_supply"
    HVAC = "hvac"
    ROOF = "roof"
    BOILER = "boiler"
    SEWER_LATERAL = "sewer_lateral"
    OTHER = "other"


class SystemStatus(str, Enum):
    REQUIRED = "required"        # known cost, must do
    CONTINGENT = "contingent"    # might do; carry as allowance


class BudgetTier(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    condition_tier: ConditionTier
    scope_description: str
    cost_per_unit: Sourced[float]
    units_count: int = Field(ge=0)

    @property
    def total(self) -> float:
        return self.cost_per_unit.value * self.units_count


class SystemLine(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    item: SystemItem
    structure_label: str | None = None   # which structure (per the profile)
    cost: Sourced[float]
    status: SystemStatus = SystemStatus.REQUIRED
    notes: str | None = None


class AbatementAllowance(BaseModel):
    """Asbestos / lead. Near-certain pre-1980; tested = verified; untested =
    assumed allowance + blocking flag."""
    model_config = ConfigDict(extra="forbid")
    amount: float = 0.0
    basis: str | None = None             # e.g. "5% of reno budget"
    tested: bool = False


class RenovationBudget(BaseModel):
    """Embedded on Deal."""
    model_config = ConfigDict(extra="forbid")

    tiers: list[BudgetTier] = Field(default_factory=list)
    make_ready_per_unit: float = 0.0     # rent-ready turn cost (cheaper than reno)
    systems: list[SystemLine] = Field(default_factory=list)
    abatement: AbatementAllowance = Field(default_factory=AbatementAllowance)
    contingency_pct: float = 0.10
    closing_costs_pct: float = 0.025     # acquisition closing % of price

    # ---- helpers --------------------------------------------------------
    @property
    def tier_total(self) -> float:
        return sum(t.total for t in self.tiers)

    @property
    def systems_total(self) -> float:
        return sum(s.cost.value for s in self.systems)

    @property
    def subtotal_before_contingency(self) -> float:
        return self.tier_total + self.systems_total + self.abatement.amount

    @property
    def total(self) -> float:
        return self.subtotal_before_contingency * (1.0 + self.contingency_pct)

    def required_contingency_floor(
        self, *, has_pre_1980: bool, systems_untested: bool
    ) -> float:
        floor = CONTINGENCY_FLOOR_BASE
        if has_pre_1980:
            floor += CONTINGENCY_BUMP_PRE_1980
        if systems_untested:
            floor += CONTINGENCY_BUMP_UNTESTED_SYSTEMS
        return round(floor, 4)
