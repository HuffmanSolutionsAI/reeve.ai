"""Pydantic mirror of `/contracts/loi_draft.schema.json`."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence


class Addressee(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    email: str  # 'format: email' enforced at the JSON schema layer
    role: str | None = None


class LoiDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["loi_draft"] = "loi_draft"
    deal_id: str
    address: str
    price: float = Field(ge=0)
    earnest_money: float | None = None
    due_diligence_days: int | None = Field(default=30, ge=0)
    financing_contingency_days: int | None = Field(default=45, ge=0)
    closing_days: int | None = Field(default=60, ge=0)
    addressee: Addressee
    terms: list[str] = Field(default_factory=list)
    narrative: str | None = None
    sent_at: str | None = None
    confidence: Confidence | None = None
