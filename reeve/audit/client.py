"""Audit clients.

Two backends behind one interface:
  - DynamoAuditClient  (prod): PutItem-only IAM enforces append-only.
  - MongoAuditClient   (dev):  same Mongo as entity store; convenient locally.

Pick via `settings.audit_backend = 'dynamo' | 'mongo'`. The factory caches
the singleton; tests can install their own via `set_default()`.
"""
from __future__ import annotations

from typing import Any, Protocol

from ..config import settings
from .events import AuditEvent, AuditKind, EntityType


def _notify(event: AuditEvent) -> None:
    """Fan an audit event out to live WebSocket subscribers (pub/sub).
    Best-effort — the audit store is the source of truth, this is just
    the live-update channel."""
    try:
        from ..api.pubsub import PUBSUB

        PUBSUB.publish(event.investor_id, event.model_dump())
    except Exception:
        # Pub/sub or the audit module aren't loaded; ignore.
        pass


class AuditClientProtocol(Protocol):
    def emit(
        self,
        *,
        investor_id: str,
        actor: str,
        kind: AuditKind,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
        detail: dict | None = None,
    ) -> AuditEvent: ...

    def write(self, event: AuditEvent) -> AuditEvent: ...

    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict[str, Any]]: ...

    def by_entity(self, entity_id: str, *, limit: int = 50) -> list[dict[str, Any]]: ...


class DynamoAuditClient:
    def __init__(self, table_name: str | None = None, region: str | None = None) -> None:
        self._table_name = table_name or settings.audit_table
        self._region = region or settings.aws_region
        self._resource = None

    def _table(self):
        if self._resource is None:
            import boto3  # deferred so importing events doesn't require AWS deps

            self._resource = boto3.resource("dynamodb", region_name=self._region)
        return self._resource.Table(self._table_name)

    def write(self, event: AuditEvent) -> AuditEvent:
        self._table().put_item(Item=event.to_item())
        _notify(event)
        return event

    def emit(self, **kw: Any) -> AuditEvent:
        event = AuditEvent(**kw)
        return self.write(event)

    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(
            KeyConditionExpression=Key("investor_id").eq(investor_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])

    def by_entity(self, entity_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(
            IndexName=settings.audit_gsi_entity,
            KeyConditionExpression=Key("entity_id").eq(entity_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])


class MongoAuditClient:
    """Sync interface (pymongo) so the runner can call .emit() without await.
    The same Mongo URI as the entity store is reused; the collection is
    `audit_events`. The dev convenience trades the IAM-enforced append-only
    of Dynamo for an application-level convention — don't issue updates from
    code paths other than this client."""

    COLLECTION = "audit_events"

    def __init__(self, uri: str | None = None, db_name: str | None = None) -> None:
        self._uri = uri or settings.mongo_uri
        self._db_name = db_name or settings.mongo_db
        self._client: Any = None

    def _coll(self):
        if self._client is None:
            from pymongo import MongoClient

            self._client = MongoClient(self._uri)
        return self._client[self._db_name][self.COLLECTION]

    def write(self, event: AuditEvent) -> AuditEvent:
        doc = event.model_dump()
        # ensure indexable fields are present at top level
        doc["ts_event_id"] = f"{event.ts}#{event.event_id}"
        try:
            self._coll().insert_one(doc)
        except Exception:
            # the runtime should never fail on audit write; surface to logs
            # in a real backend — here we suppress to keep the agent loop alive
            pass
        _notify(event)
        return event

    def emit(self, **kw: Any) -> AuditEvent:
        event = AuditEvent(**kw)
        return self.write(event)

    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self._coll()
            .find({"investor_id": investor_id})
            .sort([("ts", -1)])
            .limit(limit)
        )
        return [self._normalize(d) for d in cursor]

    def by_entity(self, entity_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        cursor = (
            self._coll()
            .find({"entity_id": entity_id})
            .sort([("ts", -1)])
            .limit(limit)
        )
        return [self._normalize(d) for d in cursor]

    @staticmethod
    def _normalize(doc: dict) -> dict:
        doc.pop("_id", None)
        return doc


_default: AuditClientProtocol | None = None


def get_audit() -> AuditClientProtocol:
    """Return the process-wide audit client per `settings.audit_backend`."""
    global _default
    if _default is None:
        backend = (settings.audit_backend or "mongo").lower()
        if backend == "dynamo":
            _default = DynamoAuditClient()
        elif backend == "mongo":
            _default = MongoAuditClient()
        else:
            raise ValueError(f"unknown audit_backend: {backend!r}")
    return _default


def set_default(client: AuditClientProtocol | None) -> None:
    """Install (or clear) the process-wide audit client. Used by tests."""
    global _default
    _default = client


def write_event(event: AuditEvent) -> AuditEvent:
    return get_audit().write(event)


# Back-compat alias for callers that imported `AuditClient` from step 1.
AuditClient = DynamoAuditClient
