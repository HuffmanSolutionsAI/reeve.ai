from __future__ import annotations

from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "dispatch",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Specialist id, e.g. 'ana'.",
            },
            "task": {
                "type": "string",
                "description": "Plain-English task for the specialist.",
            },
        },
        "required": ["agent_id", "task"],
        "additionalProperties": False,
    },
    "Route a task to a specialist and return the specialist's artifact + text.",
    reads=[],
    writes=["spawn_subagent"],
    needs_ctx=True,
)
async def dispatch(agent_id: str, task: str, _ctx: RunContext) -> dict:
    # Local imports break the runner ↔ tool cycle.
    from ..loader import load_agent
    from ..runner import run_agent
    from dataclasses import replace

    spec = load_agent(agent_id)
    sub_ctx = replace(_ctx, agent_id=None, agent_run_id=None)
    result = await run_agent(spec, task, sub_ctx)
    return {
        "agent": agent_id,
        "artifact": result.artifact,
        "text": result.text,
        "proposal_ids": result.proposal_ids,
        "status": result.status,
    }
