from __future__ import annotations

from ...contracts.deal_analysis import DealAnalysis
from ...models.artifact import ArtifactType, Confidence
from ...models.deal import DealStatus
from ...repos.artifacts import write_artifact
from ...repos.deals import set_deal_status
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


_DECISION_TO_STATUS = {
    "pursue": DealStatus.PURSUE,
    "pass": DealStatus.PASS,
    "conditional": DealStatus.ANALYZED,
}


@tool(
    "submit_deal_analysis",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": (
                    "deal_analysis payload matching "
                    "/contracts/deal_analysis.schema.json"
                ),
            },
            "deal_id": {
                "type": "string",
                "description": "Optional deal _id. If set, the deal status is updated.",
            },
        },
        "required": ["artifact"],
        "additionalProperties": False,
    },
    "Emit the deal_analysis artifact and update the pipeline. Call to finish.",
    reads=[],
    writes=["write_artifact", "set_deal_status"],
    terminal=True,
    needs_ctx=True,
)
async def submit_deal_analysis(
    artifact: dict,
    deal_id: str | None = None,
    _ctx: RunContext | None = None,
) -> dict:
    DealAnalysis.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None

    written = await write_artifact(
        type=ArtifactType.DEAL_ANALYSIS,
        payload=artifact,
        produced_by=_ctx.agent_id or "unknown",
        agent_run_id=_ctx.agent_run_id,
        deal_id=deal_id,
        confidence=Confidence(artifact["confidence"]),
        assumptions=list(artifact.get("assumptions", [])),
        unverified=list(artifact.get("unverified", [])),
    )
    if deal_id:
        decision = artifact["verdict"]["decision"]
        await set_deal_status(
            deal_id,
            _DECISION_TO_STATUS.get(decision, DealStatus.ANALYZED),
            latest_analysis_id=written.id,
        )
    return {"type": "deal_analysis", "artifact_id": written.id, **artifact}
