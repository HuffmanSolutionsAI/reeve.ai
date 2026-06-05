"""Proposals API. investor_id comes from the bearer token; path-id
endpoints cross-check that the proposal belongs to the token's investor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..audit import AuditKind, EntityType, get_audit
from ..proposals import get_client
from ..runtime.proposals import ExecutionError, execute_approved_proposal
from .auth import _assert_proposal, require_investor_id


router = APIRouter()


class Decision(BaseModel):
    approver: str = "investor"


@router.get("/proposals")
async def list_proposals(
    investor_id: str = Depends(require_investor_id),
    status: str | None = Query(None, description="pending | approved | rejected | executed"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    client = get_client()
    proposals = await client.list_for_investor(
        investor_id, status=status, limit=limit
    )
    return {
        "proposals": [p.model_dump(by_alias=True) for p in proposals],
        "investor_id": investor_id,
        "status": status,
    }


@router.get("/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: str,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    await _assert_proposal(proposal_id, investor_id)
    p = await get_client().get(proposal_id)
    return p.model_dump(by_alias=True)


@router.post("/proposals/{proposal_id}/approve")
async def approve(
    proposal_id: str,
    body: Decision,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    await _assert_proposal(proposal_id, investor_id)
    client = get_client()
    p = await client.mark_approved(proposal_id, approver=body.approver)
    if p is None:
        raise HTTPException(400, "proposal not found or not pending")
    get_audit().emit(
        investor_id=p.investor_id, actor=body.approver,
        kind=AuditKind.APPROVED,
        entity_type=EntityType.PROPOSAL, entity_id=proposal_id,
        detail={"action": p.action},
    )
    try:
        execution = await execute_approved_proposal(proposal_id)
    except ExecutionError as e:
        return {
            "proposal": p.model_dump(by_alias=True),
            "executed": False,
            "error": str(e),
        }
    return {
        "proposal": execution["proposal"],
        "executed": True,
        "result": execution["result"],
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject(
    proposal_id: str,
    body: Decision,
    investor_id: str = Depends(require_investor_id),
) -> dict:
    await _assert_proposal(proposal_id, investor_id)
    p = await get_client().mark_rejected(proposal_id, approver=body.approver)
    if p is None:
        raise HTTPException(400, "proposal not found or not pending")
    get_audit().emit(
        investor_id=p.investor_id, actor=body.approver,
        kind=AuditKind.REJECTED,
        entity_type=EntityType.PROPOSAL, entity_id=proposal_id,
        detail={"action": p.action},
    )
    return {"proposal": p.model_dump(by_alias=True)}
