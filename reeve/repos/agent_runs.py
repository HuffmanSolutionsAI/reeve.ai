from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.agent_run import AgentRun, AgentRunStatus
from ..models.artifact import Confidence
from ..models.base import now_iso


async def start_run(
    *,
    conversation_id: str | None,
    agent: str,
    task: str,
) -> AgentRun:
    run = AgentRun(
        conversation_id=conversation_id or "",
        agent=agent,
        task=task,
        started_at=now_iso(),
    )
    await db()[COLLECTIONS["agent_runs"]].insert_one(run.model_dump(by_alias=True))
    return run


async def finish_run(
    run_id: str,
    *,
    status: AgentRunStatus,
    artifact_id: str | None,
    tools_called: list[str],
    confidence: Confidence | None = None,
    proposal_ids: list[str] | None = None,
) -> None:
    updates: dict = {
        "status": status.value if hasattr(status, "value") else str(status),
        "artifact_id": artifact_id,
        "tools_called": list(tools_called),
        "proposal_ids": list(proposal_ids or []),
        "finished_at": now_iso(),
        "updated_at": now_iso(),
    }
    if confidence is not None:
        updates["confidence"] = (
            confidence.value if hasattr(confidence, "value") else str(confidence)
        )
    await db()[COLLECTIONS["agent_runs"]].update_one(
        {"_id": run_id}, {"$set": updates}
    )
