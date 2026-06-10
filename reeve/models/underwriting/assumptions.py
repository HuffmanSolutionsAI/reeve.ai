"""DealAssumptions — levers, not facts.

Provenance on every field is structurally `assumed`. The output contract
reprints these next to every number they touch. The risk register
perturbs each one and reports which moves the max offer the most."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .rent_roll import ConditionTier


class TargetRent(BaseModel):
    """Post-reno rent standard. Must be reconciled against achieved
    renovated rent + the renovated comp set."""
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    condition_tier: ConditionTier | None = None     # which tier this target applies to
    unit_mix_beds: int | None = None                # alternatively keyed by bedroom count
    monthly_rent: float = Field(ge=0)
    rationale: str | None = None


class RequiredMarginType(str, Enum):
    PCT_OF_COST = "pct_of_cost"
    DOLLARS = "dollars"


class RequiredMargin(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    margin_type: RequiredMarginType
    value: float = Field(ge=0)

    def in_dollars(self, total_cost: float) -> float:
        if self.margin_type == RequiredMarginType.PCT_OF_COST.value or (
            self.margin_type == RequiredMarginType.PCT_OF_COST
        ):
            return total_cost * self.value
        return self.value


class AncillaryKind(str, Enum):
    RUBS = "rubs"                            # ratio utility billback
    STORAGE = "storage"
    PARKING = "parking"
    CLUBHOUSE_CONVERSION = "clubhouse_conversion"   # carries HBU flag
    LAUNDRY = "laundry"
    PET_FEE = "pet_fee"
    OTHER = "other"


class AncillaryItem(BaseModel):
    """Upside inventory. Feeds the stabilized+ancillary NOI state and the
    ceiling — never the offer basis."""
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    item: AncillaryKind
    monthly: float = Field(ge=0)
    basis: str | None = None                # how the number was sized
    added_opex_annual: float = 0.0          # if the ancillary adds opex (e.g. laundry leases)
    confidence: str = "medium"              # high|medium|low — feeds risk register
    notes: str | None = None


class DealAssumptions(BaseModel):
    """Embedded on Deal. Versioned alongside each analysis artifact (the
    artifact captures a snapshot in its payload)."""
    model_config = ConfigDict(extra="forbid")

    target_rents: list[TargetRent] = Field(default_factory=list)
    exit_cap: float = Field(default=0.065, ge=0)
    required_margin: RequiredMargin = Field(
        default_factory=lambda: RequiredMargin(margin_type=RequiredMarginType.PCT_OF_COST, value=0.20)
    )
    stabilized_vacancy: float = Field(default=0.05, ge=0, le=1)
    credit_loss: float = Field(default=0.02, ge=0, le=1)
    rent_growth: float = Field(default=0.03, ge=0)        # IRR projection only
    lease_up_months: int = Field(default=12, ge=0)
    ancillary: list[AncillaryItem] = Field(default_factory=list)

    # ---- helpers --------------------------------------------------------
    def target_rent_for(self, *, tier: ConditionTier | str | None = None,
                        beds: int | None = None) -> float | None:
        """Look up a target rent by tier or by bedroom count."""
        tier_value = (
            tier if isinstance(tier, str) else (tier.value if tier else None)
        )
        # Tier-keyed match first
        for t in self.target_rents:
            t_val = (
                t.condition_tier
                if isinstance(t.condition_tier, str)
                else (t.condition_tier.value if t.condition_tier else None)
            )
            if tier_value and t_val == tier_value:
                return t.monthly_rent
        # Bed-count match
        for t in self.target_rents:
            if beds is not None and t.unit_mix_beds == beds:
                return t.monthly_rent
        # Fallback: any first target
        return self.target_rents[0].monthly_rent if self.target_rents else None

    @property
    def total_ancillary_monthly(self) -> float:
        return sum(a.monthly for a in self.ancillary)

    @property
    def total_ancillary_annual(self) -> float:
        return self.total_ancillary_monthly * 12.0

    @property
    def total_ancillary_opex_annual(self) -> float:
        return sum(a.added_opex_annual for a in self.ancillary)


class BrokerProforma(BaseModel):
    """Stored verbatim. Adversarial input. The engine rebuilds NOI from
    primitives and reports per-line deltas; this never feeds math."""
    model_config = ConfigDict(extra="forbid")

    asking_price: float | None = None
    asking_cap: float | None = None
    asking_noi: float | None = None
    rent_assumption_per_unit: float | None = None
    opex_assumption_annual: float | None = None
    om_lines: list[dict] = Field(default_factory=list)  # raw OM lines for reference
    source: str | None = None       # "OM 2026-Q2"
