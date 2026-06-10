from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.base import new_id, now_iso


class AuditKind(str, Enum):
    READ = "read"                  # any read of a sensitive collection
    ACT_INTERNAL = "act_internal"  # tier ACT_INTERNAL handler ran
    PROPOSED = "proposed"          # agent attempted gated action; proposal queued
    APPROVED = "approved"          # human approved a proposal
    REJECTED = "rejected"          # human rejected a proposal
    EXECUTED = "executed"          # execution layer ran approved proposal
    BLOCKED = "blocked"            # tool/scope rejected before execution
    ARTIFACT = "artifact"          # terminal artifact emitted


class EntityType(str, Enum):
    INVESTOR = "investor"
    PORTFOLIO = "portfolio"
    BUILDING = "building"
    UNIT = "unit"
    DEAL = "deal"
    ARTIFACT = "artifact"
    CONVERSATION = "conversation"
    MESSAGE = "message"
    AGENT_RUN = "agent_run"
    LEASE = "lease"
    TENANT = "tenant"
    VENDOR = "vendor"
    TRANSACTION = "transaction"
    REPORT = "report"
    TAX_PROFILE = "tax_profile"
    COMP = "comp"
    PROPOSAL = "proposal"
    RENT_ROLL = "rent_roll"
    OPERATING_STATEMENT = "operating_statement"
    TOOL = "tool"


def to_dynamo(value: Any) -> Any:
    """Floats must be Decimal for boto3; recurse through containers."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    if isinstance(value, tuple):
        return [to_dynamo(v) for v in value]
    return value


# Back-compat alias for callers that imported the underscore-prefixed name.
_to_dynamo = to_dynamo


class AuditEvent(BaseModel):
    """Append-only. Schema:
       PK investor_id · SK ts_event_id (= '{ts}#{event_id}', lexicographic ascending).
       GSI1 PK entity_id · SK ts_event_id — present only when entity_id is set."""

    model_config = ConfigDict(use_enum_values=True)

    event_id: str = Field(default_factory=new_id)
    ts: str = Field(default_factory=now_iso)
    investor_id: str
    actor: str  # agent id | "investor" | "execution_layer"
    kind: AuditKind
    entity_type: EntityType | None = None
    entity_id: str | None = None
    detail: dict = Field(default_factory=dict)

    @property
    def sort_key(self) -> str:
        return f"{self.ts}#{self.event_id}"

    def to_item(self) -> dict:
        item: dict = {
            "investor_id": self.investor_id,
            "ts_event_id": self.sort_key,
            "event_id": self.event_id,
            "ts": self.ts,
            "actor": self.actor,
            "kind": self.kind if isinstance(self.kind, str) else self.kind.value,
            "detail": to_dynamo(self.detail),
        }
        if self.entity_type is not None:
            item["entity_type"] = (
                self.entity_type if isinstance(self.entity_type, str) else self.entity_type.value
            )
        if self.entity_id is not None:
            item["entity_id"] = self.entity_id
        return item
