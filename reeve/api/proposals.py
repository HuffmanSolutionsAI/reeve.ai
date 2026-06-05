"""Proposals API: list, fetch, approve (and execute), reject.

This is the human side of the gate. The agent loop can only `pending`;
this endpoint is the only path to `approved` / `rejected` / `executed`.
The approve handler calls `execute_approved_proposal` synchronously and
returns the executor's result so the UI can show what shipped."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..audit import AuditKind, EntityType, get_audit
from ..proposals import get_client
from ..runtime.proposals import ExecutionError, execute_approved_proposal


router = APIRouter()


class Decision(BaseModel):
    approver: str = "investor"


@router.get("/proposals")
async def list_proposals(
    investor_id: str = Query(..., description="investor id"),
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
async def get_proposal(proposal_id: str) -> dict:
    p = await get_client().get(proposal_id)
    if p is None:
        raise HTTPException(404, "proposal not found")
    return p.model_dump(by_alias=True)


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: str, body: Decision) -> dict:
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
        # Leave the proposal in `approved`; the UI can offer a retry path.
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
async def reject(proposal_id: str, body: Decision) -> dict:
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
