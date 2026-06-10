from enum import Enum

from pydantic import Field

from .base import BaseDoc
from .underwriting import (
    BrokerProforma,
    DealAssumptions,
    DealProfile,
    FinancingScenario,
    MarketContext,
    PropertyProfile,
    RenovationBudget,
)


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

    # ---- v2 underwriting extension --------------------------------------
    # `profile` routes the engine. Existing deals (no profile field on file)
    # default to `stabilized` and run the v1 underwriter unchanged.
    profile: DealProfile = DealProfile.STABILIZED

    # Embedded entities — small, always read together, cheap to update.
    property_profile: PropertyProfile | None = None
    renovation_budget: RenovationBudget | None = None
    market_context: MarketContext | None = None
    financing_scenarios: list[FinancingScenario] = Field(default_factory=list)
    assumptions: DealAssumptions | None = None
    broker_proforma: BrokerProforma | None = None

    # Pointers to staged collections — large, ingested-from-file, lifecycle.
    active_rent_roll_id: str | None = None
    active_operating_statement_id: str | None = None
