"""Gated tools.

Calls from the agent loop are intercepted by `run_agent` and queued as
proposals — the handlers below are NEVER reached from that path. They run
ONLY via `execute_approved_proposal`, after a human approves. Credentials
for any real third-party calls (DocuSign, payment rails, etc.) live in
these handlers; agents never touch them."""
from __future__ import annotations

import os

from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...models.deal import DealStatus
from ...repos.artifacts import write_artifact
from ...repos.deals import set_deal_status
from ..capability import Tier
from ..tool import tool


@tool(
    "send_loi",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "address": {"type": "string"},
            "price": {"type": "number"},
            "earnest_money": {"type": "number"},
            "due_diligence_days": {"type": "integer"},
            "financing_contingency_days": {"type": "integer"},
            "closing_days": {"type": "integer"},
            "addressee": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "role": {"type": "string"},
                },
                "required": ["name", "email"],
            },
            "terms": {"type": "array", "items": {"type": "string"}},
            "narrative": {"type": "string"},
        },
        "required": ["deal_id", "address", "price", "addressee"],
        "additionalProperties": False,
    },
    (
        "Send a letter of intent to a seller. GATED — the runner intercepts "
        "this call from the agent loop and queues a proposal; only "
        "execute_approved_proposal runs this handler, after a human approves."
    ),
    reads=[],
    writes=["send_loi"],
)
async def send_loi(
    deal_id: str,
    address: str,
    price: float,
    addressee: dict,
    earnest_money: float | None = None,
    due_diligence_days: int = 30,
    financing_contingency_days: int = 45,
    closing_days: int = 60,
    terms: list[str] | None = None,
    narrative: str | None = None,
) -> dict:
    # Real-world send goes here. Mocked for dev — set REEVE_SEND_REAL=1 and
    # wire the docusign/email client.
    sent_at = now_iso()
    if os.getenv("REEVE_SEND_REAL"):
        raise NotImplementedError("real LOI sender not wired — implement here")

    loi_payload = {
        "type": "loi_draft",
        "deal_id": deal_id,
        "address": address,
        "price": price,
        "earnest_money": earnest_money or round(price * 0.025, 2),
        "due_diligence_days": due_diligence_days,
        "financing_contingency_days": financing_contingency_days,
        "closing_days": closing_days,
        "addressee": addressee,
        "terms": list(terms or []),
        "narrative": narrative or "",
        "sent_at": sent_at,
        "confidence": "high",
    }
    artifact = await write_artifact(
        type=ArtifactType.LOI_DRAFT,
        payload=loi_payload,
        produced_by="cole",
        agent_run_id="execution_layer",
        deal_id=deal_id,
        confidence=Confidence.HIGH,
    )
    await set_deal_status(deal_id, DealStatus.UNDER_CONTRACT)
    return {
        "sent": True,
        "sent_at": sent_at,
        "deal_id": deal_id,
        "artifact_id": artifact.id,
        "recipient": addressee,
    }
