from enum import Enum

from pydantic import Field

from .base import BaseDoc
from .artifact import Confidence


class AgentRunStatus(str, Enum):
    OK = "ok"
    LOW_CONFIDENCE = "low_confidence"
    FAILED = "failed"
    MISSING_DATA = "missing_data"


class AgentRun(BaseDoc):
    conversation_id: str
    agent: str  # agent id (ana, reeve, cole, …)
    task: str
    tools_called: list[str] = Field(default_factory=list)
    artifact_id: str | None = None
    proposal_ids: list[str] = Field(default_factory=list)
    confidence: Confidence | None = None
    status: AgentRunStatus = AgentRunStatus.OK
    started_at: str | None = None
    finished_at: str | None = None
