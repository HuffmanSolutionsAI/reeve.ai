"""Thin Dynamo client for the audit log.

The IAM role attached to the app grants `PutItem` only — `UpdateItem` and
`DeleteItem` are not permitted. The append-only guarantee lives at the IAM
layer (see `infra/cdk/stacks/audit_stack.py`), so this client deliberately
exposes no update/delete methods.
"""
from __future__ import annotations

from typing import Any

from ..config import settings
from .events import AuditEvent, AuditKind, EntityType


class AuditClient:
    def __init__(self, table_name: str | None = None, region: str | None = None) -> None:
        self._table_name = table_name or settings.audit_table
        self._region = region or settings.aws_region
        self._resource = None

    def _table(self):
        if self._resource is None:
            import boto3  # deferred so importing events doesn't require AWS deps

            self._resource = boto3.resource("dynamodb", region_name=self._region)
        return self._resource.Table(self._table_name)

    # ---- writes -------------------------------------------------------------
    def write(self, event: AuditEvent) -> AuditEvent:
        self._table().put_item(Item=event.to_item())
        return event

    def emit(
        self,
        *,
        investor_id: str,
        actor: str,
        kind: AuditKind,
        entity_type: EntityType | None = None,
        entity_id: str | None = None,
        detail: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            investor_id=investor_id,
            actor=actor,
            kind=kind,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
        )
        return self.write(event)

    # ---- reads --------------------------------------------------------------
    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Newest-first activity feed for an investor."""
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(
            KeyConditionExpression=Key("investor_id").eq(investor_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])

    def by_entity(self, entity_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Every event touching a given entity (via GSI1)."""
        from boto3.dynamodb.conditions import Key

        resp = self._table().query(
            IndexName=settings.audit_gsi_entity,
            KeyConditionExpression=Key("entity_id").eq(entity_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])


_default: AuditClient | None = None


def get_audit() -> AuditClient:
    global _default
    if _default is None:
        _default = AuditClient()
    return _default


def write_event(event: AuditEvent) -> AuditEvent:
    return get_audit().write(event)
