"""Stub schemas: defined so cross-entity references stay coherent today, fleshed
out when each owning agent is built. Indexing is intentionally minimal."""
from enum import Enum

from pydantic import BaseModel, Field

from .base import BaseDoc


# ---- ASSET MGMT --------------------------------------------------------------
class LeaseStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    PENDING = "pending"


class Lease(BaseDoc):
    investor_id: str  # convenience for query scoping
    unit_id: str
    tenant_id: str
    term_start: str | None = None  # ISO date
    term_end: str | None = None    # ISO date — drives renewal_date queries
    rent: float | None = None
    security_deposit: float | None = None
    renewal_date: str | None = None  # ISO date — when the renewal notice is due
    status: LeaseStatus = LeaseStatus.PENDING
    notes: list[str] = Field(default_factory=list)


class TenantContact(BaseModel):
    kind: str  # email | phone | other
    value: str


class Tenant(BaseDoc):
    investor_id: str  # convenience for query scoping
    name: str
    contacts: list[TenantContact] = Field(default_factory=list)
    lease_history: list[str] = Field(default_factory=list)  # → lease._id
    notes: list[str] = Field(default_factory=list)

    def email(self) -> str | None:
        for c in self.contacts:
            if c.kind == "email":
                return c.value
        return None


class Vendor(BaseDoc):
    name: str
    trades: list[str] = Field(default_factory=list)
    rates: dict = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)  # → work_order._id (future)


# ---- FINANCE & TAX -----------------------------------------------------------
class Transaction(BaseDoc):
    """Ledger row, normalized from Plaid (or manual). The same row is what
    Reed reads to compute KPIs and what Bea categorizes/reconciles."""

    investor_id: str
    building_id: str
    account_id: str | None = None
    plaid_id: str | None = None  # unique, idempotency key for sync
    date: str  # ISO date
    amount: float  # signed: positive = inflow, negative = outflow
    currency: str = "USD"
    description: str = ""
    merchant: str | None = None
    category: str | None = None  # normalized: rent | maintenance | taxes | …
    plaid_category: list[str] = Field(default_factory=list)  # raw, from Plaid
    reconciled: bool = False
    categorized_by: str | None = None  # 'rule_based' | agent_id | None
    categorized_at: str | None = None


class Report(BaseDoc):
    type: str  # cash_flow | performance | morning_brief
    period: str  # e.g. "2026-04" or "ytd-2026"
    artifact_id: str  # → artifact._id
    produced_by: str  # agent id (Reed)


class TaxProfile(BaseDoc):
    investor_id: str
    entity_structure: dict = Field(default_factory=dict)
    prior_returns: list[str] = Field(default_factory=list)  # storage refs / artifact ids
    liabilities: list[dict] = Field(default_factory=list)


# ---- SOURCING / GATING -------------------------------------------------------
class Comp(BaseDoc):
    """Comp cache; TTL via `expires_at`."""

    area_key: str  # ZIP / submarket / geohash — index this when comps land
    payload: dict
    expires_at: str | None = None


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class Proposal(BaseDoc):
    """Designed here for shape stability; the live table is built with Cole.
    When deployed, this lives in DynamoDB (PK=investor_id, SK=proposal_id, GSI on
    status#created_at). Only `execute_approved_proposal()` advances status to
    `executed`; agents may only write `pending`."""

    investor_id: str
    agent: str
    action: str  # tool name on the gated action
    payload: dict = Field(default_factory=dict)
    summary: str
    status: ProposalStatus = ProposalStatus.PENDING
    approver: str | None = None
    decided_at: str | None = None
    executed_at: str | None = None
