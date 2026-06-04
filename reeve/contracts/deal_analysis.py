"""Pydantic mirror of `/contracts/deal_analysis.schema.json`.

This is the artifact Ana emits and the UI renders for a deal card. Treat the
JSON schema file as the wire contract; this module is the runtime validator
(Ana's terminal tool serializes a DealAnalysis instance into the artifact
payload).
"""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence


class VerdictDecision(str, Enum):
    PURSUE = "pursue"
    PASS = "pass"
    CONDITIONAL = "conditional"


class DealAnalysisVerdict(BaseModel):
    decision: VerdictDecision
    max_price: float | None = None
    headline: str


class DealAnalysisMetrics(BaseModel):
    cap_in_place: float
    cap_proforma: float
    coc_year1: float
    coc_stabilized: float
    dscr: float
    avg_rent_in_place: float
    avg_rent_market: float
    rent_upside_pct: float | None = None
    rent_upside_monthly: float | None = None


class RentRollEntry(BaseModel):
    unit: str
    in_place: float
    market: float


class DealAnalysis(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")

    type: Literal["deal_analysis"] = "deal_analysis"
    address: str
    units: int = Field(ge=1)
    ask: float
    price_per_unit: float | None = None
    verdict: DealAnalysisVerdict
    metrics: DealAnalysisMetrics
    rent_roll: list[RentRollEntry] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    thesis: str
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
