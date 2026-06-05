"""Proposal store.

Lives in Mongo today and moves to DynamoDB when Cole (the first gated agent)
ships — that's where the Approvals UI will read from. The shape stays the
same; only the storage moves. Critically, only `pending` is settable from
the agent loop; `approved`/`executed` advance only via the execution layer
(see `reeve/runtime/proposals.py`)."""
from __future__ import annotations

from pymongo import ReturnDocument

from ..db.mongo import db
from ..models.base import now_iso
from ..models.stubs import Proposal, ProposalStatus


PROPOSALS_COLLECTION = "proposals"


async def write_proposal(
    *,
    investor_id: str,
    agent: str,
    action: str,
    payload: dict,
    summary: str,
) -> Proposal:
    proposal = Proposal(
        investor_id=investor_id,
        agent=agent,
        action=action,
        payload=payload,
        summary=summary,
        status=ProposalStatus.PENDING,
    )
    await db()[PROPOSALS_COLLECTION].insert_one(proposal.model_dump(by_alias=True))
    return proposal


async def get_proposal(proposal_id: str) -> Proposal | None:
    doc = await db()[PROPOSALS_COLLECTION].find_one({"_id": proposal_id})
    return Proposal.model_validate(doc) if doc else None


async def mark_approved(proposal_id: str, *, approver: str) -> Proposal | None:
    doc = await db()[PROPOSALS_COLLECTION].find_one_and_update(
        {"_id": proposal_id, "status": ProposalStatus.PENDING.value},
        {
            "$set": {
                "status": ProposalStatus.APPROVED.value,
                "approver": approver,
                "decided_at": now_iso(),
                "updated_at": now_iso(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return Proposal.model_validate(doc) if doc else None


async def mark_executed(proposal_id: str) -> Proposal | None:
    doc = await db()[PROPOSALS_COLLECTION].find_one_and_update(
        {"_id": proposal_id, "status": ProposalStatus.APPROVED.value},
        {
            "$set": {
                "status": ProposalStatus.EXECUTED.value,
                "executed_at": now_iso(),
                "updated_at": now_iso(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return Proposal.model_validate(doc) if doc else None
