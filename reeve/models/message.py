from enum import Enum

from pydantic import BaseModel, Field

from .base import BaseDoc


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Handoff(BaseModel):
    agent: str
    desk: str


class DecisionRequest(BaseModel):
    summary: str
    options: list[str] = Field(default_factory=list)


class Message(BaseDoc):
    conversation_id: str
    seq: int
    speaker: str  # "investor" | "reeve" | "<agent_id>"
    role: MessageRole
    text: str
    handoffs: list[Handoff] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    decision_request: DecisionRequest | None = None
