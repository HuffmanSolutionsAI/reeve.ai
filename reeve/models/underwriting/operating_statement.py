"""OperatingStatement — the T-12 P&L. Staged collection.

Same envelope conventions as RentRoll (source, validation, human_confirmed,
supersedes). The line items are deliberately granular: taxes and insurance
are first-class fields because the spec demands reassessment-at-trade-price
and a commercial insurance quote, not their seller-of-record substitutes."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from ..base import BaseDoc
from .provenance import Sourced
from .rent_roll import (  # reuse the envelope primitives
    IngestFormat,
    RentRollSource as IngestSource,
    RentRollValidation as Validation,
)


class OpExCategory(str, Enum):
    TAXES = "taxes"
    INSURANCE = "insurance"
    UTILITIES_WATER = "utilities_water"
    UTILITIES_ELECTRIC = "utilities_electric"
    UTILITIES_GAS = "utilities_gas"
    UTILITIES_TRASH = "utilities_trash"
    MGMT_FEE = "mgmt_fee"
    REPAIRS_MAINTENANCE = "repairs_maintenance"
    TURNS = "turns"
    PAYROLL = "payroll"
    ADMIN = "admin"
    MARKETING = "marketing"
    OTHER = "other"


class OperatingLine(BaseModel):
    """One P&L line — annual dollars, optional monthly detail."""
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    category: OpExCategory
    label: str | None = None              # subcategory if needed
    annual: Sourced[float]
    monthly: list[float] | None = None    # 12 entries when available; seasonality + spikes
    notes: str | None = None


class TaxReassessmentMethod(str, Enum):
    MILLAGE_AT_PRICE = "millage_at_price"     # millage × trade price
    LOCAL_RULE = "local_rule"                  # state/county-specific formula
    BROKER_ESTIMATE = "broker_estimate"        # adversarial; flag
    CARRIED_FORWARD = "carried_forward"        # seller's basis (always wrong on trade)


class TaxRecord(BaseModel):
    """Property tax — split out so reassessment-at-trade-price is enforced."""
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    current_assessed: Sourced[float] | None = None
    current_annual_bill: Sourced[float] | None = None
    reassessment_estimate_at_price: Sourced[float] | None = None
    reassessment_method: TaxReassessmentMethod | None = None
    millage_rate: float | None = None              # for MILLAGE_AT_PRICE reassessment per-bid
    notes: str | None = None

    def reassessed_at(self, price: float) -> float | None:
        """Recompute the tax bill at a candidate bid. Used by the sensitivity
        grid to re-derive taxes per cell."""
        if self.reassessment_method == TaxReassessmentMethod.MILLAGE_AT_PRICE.value or (
            self.reassessment_method == TaxReassessmentMethod.MILLAGE_AT_PRICE
        ):
            if self.millage_rate is not None:
                return self.millage_rate * price
        # Otherwise return the static estimate if any.
        if self.reassessment_estimate_at_price is not None:
            return self.reassessment_estimate_at_price.value
        return None


class InsuranceQuoteSource(str, Enum):
    BOUND_COMMERCIAL = "bound_commercial"      # carrier-bound — trust
    INDICATED_COMMERCIAL = "indicated_commercial"  # quote-in-process
    RESIDENTIAL_PROXY = "residential_proxy"    # invalid for 5+; flag
    SELLER_CURRENT = "seller_current"          # what they're paying now (info only)


class InsuranceRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    current_annual: Sourced[float] | None = None
    commercial_quote: Sourced[float] | None = None
    quote_source: InsuranceQuoteSource | None = None
    quote_date: str | None = None
    notes: str | None = None


class UtilityRecord(BaseModel):
    """For RUBS (ratio utility billback) candidacy and master/sub-meter map."""
    model_config = ConfigDict(extra="forbid")
    master_metered: list[str] = Field(default_factory=list)   # which utilities
    sub_metered: list[str] = Field(default_factory=list)
    owner_paid_annual: float | None = None
    rubs_candidate: bool = False
    notes: str | None = None


class OperatingPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str        # ISO date
    end: str

    def is_full_year(self) -> bool:
        # Cheap heuristic: 365 ± 5 days.
        try:
            from datetime import date
            d_start = date.fromisoformat(self.start)
            d_end = date.fromisoformat(self.end)
            return 360 <= (d_end - d_start).days <= 370
        except Exception:
            return False


class OperatingStatement(BaseDoc):
    """Staged document. Mongo collection `operating_statements`."""

    deal_id: str
    investor_id: str
    period: OperatingPeriod
    source: IngestSource = Field(default_factory=IngestSource)
    lines: list[OperatingLine] = Field(default_factory=list)
    tax: TaxRecord = Field(default_factory=TaxRecord)
    insurance: InsuranceRecord = Field(default_factory=InsuranceRecord)
    utilities: UtilityRecord = Field(default_factory=UtilityRecord)
    reserves_per_door: float = 300.0              # per-door, per-year — below NOI, in DSCR
    validation: Validation = Field(default_factory=Validation)
    human_confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: str | None = None
    supersedes: str | None = None

    # ---- helpers --------------------------------------------------------
    def annual_for(self, category: OpExCategory | str) -> float:
        cat = category if isinstance(category, str) else category.value
        return sum(
            line.annual.value for line in self.lines
            if (line.category if isinstance(line.category, str) else line.category.value) == cat
        )

    def annual_excluding(self, *exclude: OpExCategory | str) -> float:
        excl = {(c if isinstance(c, str) else c.value) for c in exclude}
        return sum(
            line.annual.value for line in self.lines
            if (line.category if isinstance(line.category, str) else line.category.value) not in excl
        )
