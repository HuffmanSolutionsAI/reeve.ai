"""Pydantic mirror of `/contracts/tax_memo.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence
from .morning_brief import Period, Severity


class StrategyKind(str, Enum):
    COST_SEGREGATION = "cost_segregation"
    SECTION_1031_EXCHANGE = "1031_exchange"
    PASSIVE_LOSS_CARRY = "passive_loss_carry"
    DEPRECIATION_RECAPTURE = "depreciation_recapture"
    ENTITY_STRUCTURE = "entity_structure"
    DEDUCTION_OPPORTUNITY = "deduction_opportunity"
    FILING_DEADLINE = "filing_deadline"
    AUDIT_RISK = "audit_risk"


class TaxEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gross_rental_income: float
    operating_expenses: float
    depreciation: float
    net_rental_income: float
    federal_rate: float | None = None
    state_rate: float | None = None
    federal_liability: float
    state_liability: float
    total_liability: float


class BuildingTaxLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    building_id: str
    address: str
    gross_rental_income: float | None = None
    operating_expenses: float | None = None
    depreciation: float | None = None
    net_rental_income: float


class StrategyFlag(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    kind: StrategyKind
    severity: Severity | None = None
    text: str
    estimated_value: float | None = None


class TaxMemo(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["tax_memo"] = "tax_memo"
    as_of: str
    tax_year: int = Field(ge=2000, le=2100)
    period: Period | None = None
    estimate: TaxEstimate
    by_building: list[BuildingTaxLine] = Field(default_factory=list)
    strategy_flags: list[StrategyFlag] = Field(default_factory=list)
    filing_due: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    thesis: str
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
