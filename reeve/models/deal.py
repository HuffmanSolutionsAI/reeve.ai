from enum import Enum

from pydantic import Field

from .base import BaseDoc


class DealStatus(str, Enum):
    SOURCED = "sourced"
    ANALYZED = "analyzed"
    PURSUE = "pursue"
    PASS = "pass"
    UNDER_CONTRACT = "under_contract"
    CLOSED = "closed"


class DealSource(str, Enum):
    SAM = "sam"
    MANUAL = "manual"
    BROKER = "broker"


class Deal(BaseDoc):
    investor_id: str
    address: str
    units: int | None = None
    ask: float | None = None
    source: DealSource = DealSource.MANUAL
    status: DealStatus = DealStatus.SOURCED
    latest_analysis_id: str | None = None  # → artifact._id
    notes: list[str] = Field(default_factory=list)
