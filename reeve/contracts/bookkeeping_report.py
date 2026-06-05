"""Pydantic mirror of `/contracts/bookkeeping_report.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence
from .morning_brief import Period, Severity


class AnomalyKind(str, Enum):
    AMOUNT_OUTLIER = "amount_outlier"
    MISSING_CATEGORY = "missing_category"
    DUPLICATE = "duplicate"
    DATE_ANOMALY = "date_anomaly"
    UNCATEGORIZED = "uncategorized"
    MISSING_RECEIPT = "missing_receipt"


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    kind: AnomalyKind
    severity: Severity | None = None
    text: str
    transaction_id: str | None = None
    amount: float | None = None
    building_id: str | None = None


class BookkeepingReport(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["bookkeeping_report"] = "bookkeeping_report"
    as_of: str
    period: Period
    reviewed: int = Field(ge=0)
    recategorized: int = Field(default=0, ge=0)
    adjusting_entries_proposed: int = Field(default=0, ge=0)
    category_distribution: dict[str, int] = Field(default_factory=dict)
    anomalies: list[Anomaly] = Field(default_factory=list)
    thesis: str
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
