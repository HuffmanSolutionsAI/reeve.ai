"""Pydantic mirror of `/contracts/morning_brief.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence


class HighlightKind(str, Enum):
    VACANCY = "vacancy"
    DELINQUENCY = "delinquency"
    ANOMALY = "anomaly"
    EXPENSE = "expense"
    ACTIVITY = "activity"
    WATCH = "watch"


class Severity(str, Enum):
    INFO = "info"
    WATCH = "watch"
    ACTION = "action"


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str
    end: str


class PortfolioSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buildings: int = Field(ge=0)
    units: int = Field(ge=0)
    occupied: int = Field(ge=0)
    vacant: int | None = Field(default=None, ge=0)
    occupancy: float = Field(ge=0.0, le=1.0)


class MonthToDate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revenue: float
    expenses: float
    noi: float
    expense_ratio: float | None = None
    by_category: dict[str, float] | None = None


class CashPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operating: float | None = None
    reserves: float | None = None
    total: float | None = None


class Highlight(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    kind: HighlightKind
    severity: Severity | None = None
    text: str
    building_id: str | None = None
    amount: float | None = None


class MorningBrief(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    type: Literal["morning_brief"] = "morning_brief"
    as_of: str
    period: Period
    portfolio: PortfolioSummary
    month_to_date: MonthToDate
    cash_position: CashPosition | None = None
    highlights: list[Highlight] = Field(default_factory=list)
    thesis: str
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
