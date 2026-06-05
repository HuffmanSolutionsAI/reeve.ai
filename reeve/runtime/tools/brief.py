from __future__ import annotations

from ...contracts.morning_brief import MorningBrief
from ...models.artifact import ArtifactType, Confidence
from ...repos.artifacts import write_artifact
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "submit_morning_brief",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": (
                    "morning_brief payload matching "
                    "/contracts/morning_brief.schema.json"
                ),
            },
        },
        "required": ["artifact"],
        "additionalProperties": False,
    },
    (
        "Emit the morning_brief artifact. Reed's terminal tool — call to finish."
    ),
    reads=[],
    writes=["write_artifact"],
    terminal=True,
    needs_ctx=True,
)
async def submit_morning_brief(
    artifact: dict, _ctx: RunContext | None = None,
) -> dict:
    MorningBrief.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None
    written = await write_artifact(
        type=ArtifactType.MORNING_BRIEF,
        payload=artifact,
        produced_by=_ctx.agent_id or "unknown",
        agent_run_id=_ctx.agent_run_id,
        confidence=Confidence(artifact["confidence"]),
        unverified=list(artifact.get("unverified", [])),
    )
    return {
        "type": "morning_brief",
        "artifact_id": written.id,
        "version": written.version,
        **artifact,
    }
