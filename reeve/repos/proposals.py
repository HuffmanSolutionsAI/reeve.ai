"""Thin compatibility shim.

Proposals moved to `reeve/proposals/` so a single Protocol can sit in front
of both Mongo (dev) and DynamoDB (prod). This module re-exports the names
older callers (and tests) reach for, forwarding to the configured client."""
from __future__ import annotations

from ..models.stubs import Proposal
from ..proposals import get_client


PROPOSALS_COLLECTION = "proposals"  # MongoProposalsClient's collection


async def write_proposal(
    *,
    investor_id: str,
    agent: str,
    action: str,
    payload: dict,
    summary: str,
) -> Proposal:
    return await get_client().write(
        investor_id=investor_id, agent=agent, action=action,
        payload=payload, summary=summary,
    )


async def get_proposal(proposal_id: str) -> Proposal | None:
    return await get_client().get(proposal_id)


async def mark_approved(proposal_id: str, *, approver: str) -> Proposal | None:
    return await get_client().mark_approved(proposal_id, approver=approver)


async def mark_rejected(proposal_id: str, *, approver: str) -> Proposal | None:
    return await get_client().mark_rejected(proposal_id, approver=approver)


async def mark_executed(proposal_id: str) -> Proposal | None:
    return await get_client().mark_executed(proposal_id)
