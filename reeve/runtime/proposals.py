"""Execution layer for approved proposals — NOT reachable from an agent loop.

This is where credentials live. Agents can only write `pending` proposals via
`write_proposal`. A human approves (sets status to `approved`); only this
function runs the corresponding handler and advances the proposal to
`executed`."""
from __future__ import annotations

import inspect
from typing import Any

from ..audit import AuditKind, EntityType, get_audit
from ..models.stubs import ProposalStatus
from ..repos.proposals import get_proposal, mark_executed
from .tool import REGISTRY


class ExecutionError(RuntimeError):
    pass


async def execute_approved_proposal(proposal_id: str) -> Any:
    proposal = await get_proposal(proposal_id)
    if proposal is None:
        raise ExecutionError(f"proposal {proposal_id} not found")
    if str(proposal.status) != ProposalStatus.APPROVED.value:
        raise ExecutionError(
            f"proposal {proposal_id} status={proposal.status}, expected approved"
        )

    tool = REGISTRY.get(proposal.action)
    if tool is None:
        raise ExecutionError(f"action '{proposal.action}' not registered")

    handler = tool.handler
    result = (
        await handler(**proposal.payload)
        if inspect.iscoroutinefunction(handler)
        else handler(**proposal.payload)
    )

    await mark_executed(proposal_id)
    get_audit().emit(
        investor_id=proposal.investor_id,
        actor="execution_layer",
        kind=AuditKind.EXECUTED,
        entity_type=EntityType.PROPOSAL,
        entity_id=proposal_id,
        detail={"action": proposal.action},
    )
    return result
