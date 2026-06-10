from enum import Enum

from pydantic import Field

from .base import BaseDoc


class ArtifactType(str, Enum):
    DEAL_ANALYSIS = "deal_analysis"
    VALUE_ADD_ANALYSIS = "value_add_analysis"
    REPORT = "report"
    MORNING_BRIEF = "morning_brief"
    CASH_FLOW_REPORT = "cash_flow_report"
    LOI_DRAFT = "loi_draft"
    SOURCING_SUMMARY = "sourcing_summary"
    BOOKKEEPING_REPORT = "bookkeeping_report"
    TENANT_MESSAGE = "tenant_message"
    WORK_ORDER = "work_order"
    LISTING = "listing"
    DILIGENCE = "diligence"
    TAX_MEMO = "tax_memo"
    MESSAGE_DRAFT = "message_draft"
    LISTING_DRAFT = "listing_draft"
    WORK_ORDER_DRAFT = "work_order_draft"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Artifact(BaseDoc):
    """Immutable, versioned. A revision is a NEW document with `supersedes` set."""

    type: ArtifactType
    version: int = 1
    produced_by: str  # agent id
    agent_run_id: str

    payload: dict  # the output contract (see /contracts/*.schema.json)
    inputs: dict = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    unverified: list[str] = Field(default_factory=list)

    deal_id: str | None = None
    supersedes: str | None = None  # prior artifact._id this revision replaces
