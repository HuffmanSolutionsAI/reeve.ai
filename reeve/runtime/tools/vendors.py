"""Manny's tools: find vendors for a trade, dispatch one (GATED).
The gated handler resolves the vendor's contact at send time and
writes the work_order artifact."""
from __future__ import annotations

from ...contracts.work_order import WorkOrder
from ...db.mongo import COLLECTIONS, db
from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...repos.artifacts import write_artifact
from ...repos.vendors import get_vendor, list_vendors_by_trade as repo_list
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "list_vendors_by_trade",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "trade": {"enum": ["plumbing", "hvac", "electrical", "general",
                               "painting", "landscaping", "appliance", "roofing"]},
        },
        "required": ["trade"],
        "additionalProperties": False,
    },
    (
        "Return active vendors for a trade in the investor's roster. "
        "Vendor contact info is exposed here so Manny can pick one and "
        "compose the dispatch."
    ),
    reads=["vendor"],
    needs_ctx=True,
)
async def list_vendors_by_trade(
    trade: str, _ctx: RunContext | None = None,
) -> dict:
    assert _ctx is not None
    vendors = await repo_list(_ctx.investor_id, trade)
    return {
        "trade": trade,
        "count": len(vendors),
        "vendors": [
            {
                "id": v.id, "name": v.name, "trades": list(v.trades),
                "contact_email": v.contact_email, "contact_phone": v.contact_phone,
                "rates": dict(v.rates), "active": v.active,
            }
            for v in vendors
        ],
    }


@tool(
    "dispatch_vendor",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "vendor_id": {"type": "string"},
            "building_id": {"type": "string"},
            "unit_id": {"type": "string"},
            "trade": {"enum": ["plumbing", "hvac", "electrical", "general",
                               "painting", "landscaping", "appliance", "roofing"]},
            "scope": {"type": "string", "description": "What the vendor is being asked to do."},
            "priority": {"enum": ["emergency", "urgent", "standard", "low"]},
            "max_spend": {"type": "number", "description": "Optional cap on the vendor's authorization."},
        },
        "required": ["vendor_id", "building_id", "trade", "scope", "priority"],
        "additionalProperties": False,
    },
    (
        "Dispatch a vendor to a work site. GATED — the runner intercepts "
        "and queues a proposal; only execute_approved_proposal runs this "
        "handler, after a human approves. The handler 'sends' the dispatch "
        "and writes the work_order artifact."
    ),
    reads=[],
    writes=["dispatch_vendor"],
)
async def dispatch_vendor(
    vendor_id: str,
    building_id: str,
    trade: str,
    scope: str,
    priority: str,
    unit_id: str | None = None,
    max_spend: float | None = None,
) -> dict:
    vendor = await get_vendor(vendor_id)
    if vendor is None:
        raise ValueError(f"vendor {vendor_id!r} not found")
    if not vendor.active:
        raise ValueError(f"vendor {vendor_id!r} is inactive")
    if trade not in vendor.trades:
        raise ValueError(f"vendor {vendor.name!r} does not list trade {trade!r}")

    building = await db()[COLLECTIONS["buildings"]].find_one({"_id": building_id})
    if building is None:
        raise ValueError(f"building {building_id!r} not found")

    unit_label = None
    if unit_id:
        unit_doc = await db()[COLLECTIONS["units"]].find_one({"_id": unit_id})
        if unit_doc:
            unit_label = unit_doc.get("label")

    dispatched_at = now_iso()
    payload = {
        "type": "work_order",
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "building_id": building_id,
        "building_address": building.get("address"),
        "unit_id": unit_id,
        "unit_label": unit_label,
        "trade": trade,
        "scope": scope,
        "priority": priority,
        "max_spend": max_spend,
        "dispatched_at": dispatched_at,
        "contact": {
            "email": vendor.contact_email,
            "phone": vendor.contact_phone,
        },
    }
    WorkOrder.model_validate(payload)

    artifact = await write_artifact(
        type=ArtifactType.WORK_ORDER,
        payload=payload,
        produced_by="manny",
        agent_run_id="execution_layer",
        confidence=Confidence.HIGH,
    )
    return {
        "dispatched": True,
        "dispatched_at": dispatched_at,
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "building_id": building_id,
        "unit_id": unit_id,
        "artifact_id": artifact.id,
    }
