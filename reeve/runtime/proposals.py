"""The execution layer for approved proposals.

This is the only place the gated handlers in `REGISTRY` are ever invoked.
Agents can only queue proposals (status=`pending`) via the runner's
intercept; this function (driven by the API approve endpoint) is what
flips them to `executed` and runs the real handler. Credentials for the
real third-party calls (DocuSign, payment rails, etc.) live in those
handlers — agents never touch them."""
from __future__ import annotations

import inspect
from typing import Any

from ..audit import AuditKind, EntityType, get_audit
from ..models.stubs import ProposalStatus
from ..proposals import get_client as get_proposals_client
from .tool import REGISTRY


class ExecutionError(RuntimeError):
    pass


async def execute_approved_proposal(proposal_id: str) -> dict:
    """Run an approved proposal. Returns a dict with `proposal` (the final
    Proposal record) and `result` (whatever the handler returned)."""
    client = get_proposals_client()
    proposal = await client.get(proposal_id)
    if proposal is None:
        raise ExecutionError(f"proposal {proposal_id!r} not found")
    status = proposal.status if isinstance(proposal.status, str) else proposal.status.value
    if status != ProposalStatus.APPROVED.value:
        raise ExecutionError(
            f"proposal {proposal_id!r} is {status!r}, expected approved"
        )

    tool = REGISTRY.get(proposal.action)
    if tool is None:
        raise ExecutionError(f"action {proposal.action!r} not registered")

    handler = tool.handler
    try:
        result = (
            await handler(**proposal.payload)
            if inspect.iscoroutinefunction(handler)
            else handler(**proposal.payload)
        )
    except Exception as e:
        # Leave the proposal in `approved` so it can be retried; surface the
        # error to the caller. Audit captures the failed execution attempt.
        get_audit().emit(
            investor_id=proposal.investor_id,
            actor="execution_layer",
            kind=AuditKind.BLOCKED,
            entity_type=EntityType.PROPOSAL,
            entity_id=proposal_id,
            detail={"action": proposal.action, "error": str(e)},
        )
        raise ExecutionError(f"execution of {proposal.action!r} failed: {e}") from e

    executed = await client.mark_executed(proposal_id)
    get_audit().emit(
        investor_id=proposal.investor_id,
        actor="execution_layer",
        kind=AuditKind.EXECUTED,
        entity_type=EntityType.PROPOSAL,
        entity_id=proposal_id,
        detail={"action": proposal.action},
    )
    return {
        "proposal": (executed or proposal).model_dump(by_alias=True),
        "result": result if isinstance(result, (dict, list, str, int, float, bool)) or result is None
                  else str(result),
    }
