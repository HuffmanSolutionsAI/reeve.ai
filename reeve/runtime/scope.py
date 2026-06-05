"""Scope vocabulary the loader validates against and the runner enforces.

Growing this set is intentional: a new agent's scope labels must land here
first or the loader will refuse to build the spec. That is the point — every
new permission gets a deliberate code change."""
from __future__ import annotations

from .capability import Tier
from .tool import Tool


# ---- known scope labels -----------------------------------------------------
KNOWN_READ_SCOPES: set[str] = {
    # core
    "investor", "buy_box", "portfolio", "building", "unit", "deal", "comp",
    "artifact", "conversation", "message", "audit",
    # sensitive (stub collections; reads MUST audit)
    "lease", "tenant", "vendor", "transaction", "report", "tax_profile",
    # external surfaces
    "duckdb_pipeline",
}

# Reads from these labels trigger a `read` audit event in the runner.
SENSITIVE_READS: set[str] = {"lease", "tenant", "transaction", "tax_profile"}

KNOWN_INTERNAL_ACTIONS: set[str] = {
    "write_artifact",
    "post_message",
    "update_investor_context",
    "set_deal_status",
    "create_deal",
    "draft_message",
    "draft_listing",
    "draft_renewal",
    "create_work_order_draft",
    "save_applicant_notes",
    "categorize_transaction",
    "spawn_subagent",
}

KNOWN_GATED_ACTIONS: set[str] = {
    # acquisition
    "send_loi",
    "send_offer",
    "set_deal_under_contract",
    "order_paid_report",
    # asset management
    "send_tenant_message",
    "dispatch_vendor",
    "authorize_spend",
    "post_listing",
    "send_renewal_offer",
    "send_applicant_decision",
    # finance & tax
    "post_adjusting_entry",
    "submit_tax_filing",
}


# ---- runtime enforcement ----------------------------------------------------
def check_scope(spec, t: Tool) -> str | None:
    """Return a violation reason string if the tool exceeds the agent's
    granted scopes; None if it's permitted."""
    for r in t.reads:
        if r not in spec.read_scope:
            return f"read scope '{r}' not granted to {spec.id}"
    if t.tier is Tier.ACT_INTERNAL:
        for w in t.writes:
            if w not in spec.internal_actions:
                return f"internal action '{w}' not granted to {spec.id}"
    if t.tier is Tier.ACT_GATED:
        for w in t.writes:
            if w not in spec.gated_actions:
                return f"gated action '{w}' not granted to {spec.id}"
    return None
