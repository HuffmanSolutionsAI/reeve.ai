"""Cara's tools: find a lease/tenant for a unit (sensitive READ on
both), list leases due for renewal, and send a tenant message (GATED)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...contracts.tenant_message import TenantMessage
from ...db.mongo import COLLECTIONS, db
from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...repos.artifacts import write_artifact
from ...repos.leases import active_lease_for_unit, get_lease
from ...repos.tenants import get_tenant
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


def _tenant_payload(t: Any) -> dict:
    """Return the subset of Tenant fields the agent should see. PII like the
    full contact list is summarized; the email is exposed so Cara can name
    the channel, but the runner audits this read regardless."""
    return {
        "id": t.id,
        "name": t.name,
        "email": t.email(),
        "contact_kinds": sorted({c.kind for c in t.contacts}),
        "notes_count": len(t.notes),
    }


def _lease_payload(l: Any) -> dict:
    return {
        "id": l.id,
        "unit_id": l.unit_id,
        "tenant_id": l.tenant_id,
        "term_start": l.term_start,
        "term_end": l.term_end,
        "rent": l.rent,
        "renewal_date": l.renewal_date,
        "status": l.status if isinstance(l.status, str) else l.status.value,
    }


@tool(
    "find_lease_for_unit",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "building_id": {"type": "string"},
            "unit_label": {"type": "string", "description": "e.g. '2B'"},
        },
        "required": ["building_id", "unit_label"],
        "additionalProperties": False,
    },
    (
        "Resolve a unit to its current active lease + tenant. Reads `lease` "
        "and `tenant` (both sensitive — every call audits)."
    ),
    reads=["building", "unit", "lease", "tenant"],
    needs_ctx=True,
)
async def find_lease_for_unit(
    building_id: str, unit_label: str, _ctx: RunContext | None = None,
) -> dict:
    unit_doc = await db()[COLLECTIONS["units"]].find_one(
        {"building_id": building_id, "label": unit_label},
    )
    if unit_doc is None:
        return {"found": False, "reason": f"unit {unit_label!r} not in building {building_id!r}"}

    lease = await active_lease_for_unit(unit_doc["_id"])
    if lease is None:
        return {
            "found": False,
            "reason": "no active lease on this unit",
            "unit": {"id": unit_doc["_id"], "label": unit_doc["label"], "status": unit_doc["status"]},
        }

    tenant = await get_tenant(lease.tenant_id)
    if tenant is None:
        return {
            "found": False,
            "reason": "lease references a missing tenant",
            "unit": {"id": unit_doc["_id"], "label": unit_doc["label"]},
            "lease": _lease_payload(lease),
        }

    return {
        "found": True,
        "unit": {
            "id": unit_doc["_id"], "label": unit_doc["label"],
            "status": unit_doc["status"], "market_rent": unit_doc.get("market_rent"),
            "building_id": building_id,
        },
        "lease": _lease_payload(lease),
        "tenant": _tenant_payload(tenant),
    }


@tool(
    "list_leases_due_for_renewal",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "minimum": 1, "maximum": 365,
                "description": "Renewal_date within this many days from today.",
            },
        },
        "additionalProperties": False,
    },
    (
        "List leases for the investor whose renewal_date falls within "
        "`days_ahead` of today. Sensitive read on lease — every call audits."
    ),
    reads=["lease"],
    needs_ctx=True,
)
async def list_leases_due_for_renewal(
    days_ahead: int = 60, _ctx: RunContext | None = None,
) -> dict:
    assert _ctx is not None
    today = datetime.now(timezone.utc).date()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    cursor = db()[COLLECTIONS["leases"]].find(
        {
            "investor_id": _ctx.investor_id,
            "status": "active",
            "renewal_date": {"$lte": cutoff, "$gte": today.isoformat()},
        },
    ).sort([("renewal_date", 1)])
    leases: list[dict] = []
    async for doc in cursor:
        leases.append({
            "id": doc["_id"],
            "unit_id": doc["unit_id"],
            "tenant_id": doc["tenant_id"],
            "term_end": doc.get("term_end"),
            "renewal_date": doc.get("renewal_date"),
            "rent": doc.get("rent"),
        })
    return {"leases": leases, "count": len(leases), "days_ahead": days_ahead}


@tool(
    "send_tenant_message",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "tenant_id": {"type": "string"},
            "lease_id": {"type": "string"},
            "unit_id": {"type": "string"},
            "building_id": {"type": "string"},
            "channel": {"enum": ["email", "sms"]},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "purpose": {"enum": ["renewal_notice", "rent_reminder", "maintenance_update", "compliance", "general"]},
        },
        "required": ["tenant_id", "channel", "subject", "body", "purpose"],
        "additionalProperties": False,
    },
    (
        "Send a message to a tenant. GATED — the runner intercepts and queues "
        "a proposal; only execute_approved_proposal sends, after a human "
        "approves. The handler writes a tenant_message artifact on send."
    ),
    reads=[],
    writes=["send_tenant_message"],
)
async def send_tenant_message(
    tenant_id: str,
    channel: str,
    subject: str,
    body: str,
    purpose: str,
    lease_id: str | None = None,
    unit_id: str | None = None,
    building_id: str | None = None,
) -> dict:
    tenant = await get_tenant(tenant_id)
    if tenant is None:
        raise ValueError(f"tenant {tenant_id!r} not found")
    to: str | None = None
    if channel == "email":
        to = tenant.email()
    else:
        for c in tenant.contacts:
            if c.kind == "phone":
                to = c.value
                break
    if not to:
        raise ValueError(
            f"tenant {tenant_id!r} has no {channel} contact on file"
        )

    sent_at = now_iso()
    # Real send hook lives here; mocked for dev.
    payload = {
        "type": "tenant_message",
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "lease_id": lease_id,
        "unit_id": unit_id,
        "building_id": building_id,
        "channel": channel,
        "to": to,
        "subject": subject,
        "body": body,
        "purpose": purpose,
        "sent_at": sent_at,
    }
    TenantMessage.model_validate(payload)

    artifact = await write_artifact(
        type=ArtifactType.TENANT_MESSAGE,
        payload=payload,
        produced_by="cara",
        agent_run_id="execution_layer",
        confidence=Confidence.HIGH,
    )
    return {
        "sent": True,
        "sent_at": sent_at,
        "channel": channel,
        "to": to,
        "tenant_id": tenant_id,
        "artifact_id": artifact.id,
    }
