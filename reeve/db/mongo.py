"""Mongo client + collection registry + index spec.

The collection registry is the single place that names every Mongo collection.
The index spec mirrors §3 of the build plan; `ensure_indexes()` is idempotent
and safe to call at startup.

A read of any collection in `SENSITIVE_COLLECTIONS` MUST write an audit event;
the access layer (added with each agent) is responsible for enforcing that.
"""
from __future__ import annotations

from typing import Any

from ..config import settings


# ---- collection names -------------------------------------------------------
# Plural snake_case. Referenced everywhere by name through this registry.
COLLECTIONS = {
    # deep
    "investors": "investors",
    "portfolios": "portfolios",
    "buildings": "buildings",
    "units": "units",
    "deals": "deals",
    "artifacts": "artifacts",
    "conversations": "conversations",
    "messages": "messages",
    "agent_runs": "agent_runs",
    # stubs
    "leases": "leases",
    "tenants": "tenants",
    "vendors": "vendors",
    "transactions": "transactions",
    "reports": "reports",
    "tax_profiles": "tax_profiles",
    "comps": "comps",
    # runtime-adjacent collections
    "proposals": "proposals",
    "audit_events": "audit_events",  # used by MongoAuditClient (local dev)
}


# ---- index spec (mirrors §3 of the build plan) ------------------------------
# Plain tuples so this module imports without PyMongo. `ensure_indexes()`
# converts each entry to a pymongo.IndexModel at startup.
#   { collection: [ {"keys": [(field, dir), ...], "name": "...", **opts}, ... ] }
INDEX_SPECS: dict[str, list[dict[str, Any]]] = {
    "investors": [],
    "portfolios": [{"keys": [("investor_id", 1)], "name": "investor_id"}],
    "buildings": [{"keys": [("portfolio_id", 1)], "name": "portfolio_id"}],
    "units": [{"keys": [("building_id", 1)], "name": "building_id"}],
    "deals": [
        {"keys": [("investor_id", 1)], "name": "investor_id"},
        {"keys": [("status", 1)], "name": "status"},
        {"keys": [("investor_id", 1), ("status", 1)], "name": "investor_id_status"},
    ],
    "artifacts": [
        {"keys": [("deal_id", 1)], "name": "deal_id"},
        {"keys": [("type", 1)], "name": "type"},
        {"keys": [("produced_by", 1)], "name": "produced_by"},
    ],
    "conversations": [{"keys": [("investor_id", 1)], "name": "investor_id"}],
    "messages": [
        {
            "keys": [("conversation_id", 1), ("seq", 1)],
            "name": "conversation_id_seq",
            "unique": True,
        }
    ],
    "agent_runs": [
        {"keys": [("conversation_id", 1)], "name": "conversation_id"},
        {"keys": [("agent", 1)], "name": "agent"},
    ],
    # stubs — minimal until each owning agent ships
    "leases": [
        {"keys": [("investor_id", 1)], "name": "investor_id"},
        {"keys": [("unit_id", 1)], "name": "unit_id"},
        {"keys": [("tenant_id", 1)], "name": "tenant_id"},
        {"keys": [("renewal_date", 1)], "name": "renewal_date"},
    ],
    "tenants": [
        {"keys": [("investor_id", 1)], "name": "investor_id"},
    ],
    "vendors": [],
    "transactions": [
        {"keys": [("investor_id", 1), ("date", -1)], "name": "investor_date"},
        {"keys": [("building_id", 1), ("date", -1)], "name": "building_date"},
        # sparse so manual rows (no plaid_id) don't collide on the unique key
        {"keys": [("plaid_id", 1)], "name": "plaid_id",
         "unique": True, "sparse": True},
    ],
    "reports": [],
    "tax_profiles": [],
    "comps": [],
    # runtime
    "proposals": [
        {"keys": [("investor_id", 1)], "name": "investor_id"},
        {"keys": [("status", 1)], "name": "status"},
    ],
    "audit_events": [
        # Mirrors the Dynamo PK/SK: feed by investor newest-first, by entity newest-first.
        {"keys": [("investor_id", 1), ("ts", -1)], "name": "investor_ts"},
        {"keys": [("entity_id", 1), ("ts", -1)], "name": "entity_ts"},
    ],
}


SENSITIVE_COLLECTIONS = {"leases", "tenants", "transactions", "tax_profiles"}


_client = None  # type: ignore[var-annotated]


def get_client():
    """Return the process-wide AsyncIOMotorClient. Imported lazily."""
    global _client
    if _client is None:
        from motor.motor_asyncio import AsyncIOMotorClient

        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def db():
    return get_client()[settings.mongo_db]


async def ensure_indexes() -> None:
    """Create every index in INDEX_SPECS. Idempotent."""
    from pymongo import IndexModel

    target = db()
    for collection, specs in INDEX_SPECS.items():
        if not specs:
            continue
        models = [
            IndexModel(s["keys"], **{k: v for k, v in s.items() if k != "keys"}) for s in specs
        ]
        await target[COLLECTIONS[collection]].create_indexes(models)
