"""Pydantic mirror of `/contracts/sourcing_summary.schema.json`."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence


class SourcingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    units: int = Field(ge=1)
    ask: float = Field(ge=0)
    year_built: int | None = None
    distress_signal: str | None = None
    fit_score: float = Field(ge=0.0, le=1.0)
    rationale: str
    # Sam's profile classification — routes Ana's underwriter downstream.
    profile: Literal["stabilized", "value_add", "distressed"] | None = None
    duplicate: bool = False
    deal_id: str | None = None


class SourcingSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["sourcing_summary"] = "sourcing_summary"
    as_of: str
    filters: dict = Field(default_factory=dict)
    scanned: int = Field(default=0, ge=0)
    duplicates: int = Field(default=0, ge=0)
    surfaced: int = Field(default=0, ge=0)
    candidates: list[SourcingCandidate] = Field(default_factory=list)
    thesis: str
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
