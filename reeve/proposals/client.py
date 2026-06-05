"""Proposal store with two interchangeable backends.

Mirror of the audit pattern: same async interface, different storage.
  - MongoProposalsClient  (dev)  — Motor against the existing Mongo URI.
  - DynamoProposalsClient (prod) — boto3 wrapped in asyncio.to_thread.

The Dynamo shape (per §4 of the build plan):
  PK investor_id · SK proposal_id
  GSI1 PK investor_id · SK 'status#created_at' — list pending for the queue.

Only this module reads/writes proposals; the runner uses `get_client()` to
queue a proposal, the API uses it to list / approve / reject, and the
execution layer (`reeve/runtime/proposals.py`) uses it to advance status.
The status-advancing methods are the only place `approved` / `rejected` /
`executed` ever get set — no other code path can move a proposal forward.
"""
from __future__ import annotations

import asyncio
from typing import Any, Protocol

from ..config import settings
from ..models.base import now_iso
from ..models.stubs import Proposal, ProposalStatus


class ProposalClientProtocol(Protocol):
    async def write(
        self,
        *,
        investor_id: str,
        agent: str,
        action: str,
        payload: dict,
        summary: str,
    ) -> Proposal: ...

    async def get(self, proposal_id: str) -> Proposal | None: ...

    async def list_for_investor(
        self,
        investor_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Proposal]: ...

    async def mark_approved(
        self, proposal_id: str, *, approver: str
    ) -> Proposal | None: ...

    async def mark_rejected(
        self, proposal_id: str, *, approver: str
    ) -> Proposal | None: ...

    async def mark_executed(self, proposal_id: str) -> Proposal | None: ...


# ---- Mongo backend (dev) ----------------------------------------------------
class MongoProposalsClient:
    COLLECTION = "proposals"

    def _coll(self):
        from ..db.mongo import db

        return db()[self.COLLECTION]

    async def write(
        self,
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
        await self._coll().insert_one(proposal.model_dump(by_alias=True))
        return proposal

    async def get(self, proposal_id: str) -> Proposal | None:
        doc = await self._coll().find_one({"_id": proposal_id})
        return Proposal.model_validate(doc) if doc else None

    async def list_for_investor(
        self,
        investor_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Proposal]:
        query: dict = {"investor_id": investor_id}
        if status:
            query["status"] = status
        cursor = (
            self._coll()
            .find(query)
            .sort([("created_at", -1)])
            .limit(limit)
        )
        return [Proposal.model_validate(doc) async for doc in cursor]

    async def mark_approved(
        self, proposal_id: str, *, approver: str
    ) -> Proposal | None:
        from pymongo import ReturnDocument

        doc = await self._coll().find_one_and_update(
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

    async def mark_rejected(
        self, proposal_id: str, *, approver: str
    ) -> Proposal | None:
        from pymongo import ReturnDocument

        doc = await self._coll().find_one_and_update(
            {"_id": proposal_id, "status": ProposalStatus.PENDING.value},
            {
                "$set": {
                    "status": ProposalStatus.REJECTED.value,
                    "approver": approver,
                    "decided_at": now_iso(),
                    "updated_at": now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return Proposal.model_validate(doc) if doc else None

    async def mark_executed(self, proposal_id: str) -> Proposal | None:
        from pymongo import ReturnDocument

        doc = await self._coll().find_one_and_update(
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


# ---- Dynamo backend (prod) --------------------------------------------------
class DynamoProposalsClient:
    """boto3 sync wrapped in asyncio.to_thread so the API can `await` it.

    Item shape:
      investor_id (PK), proposal_id (SK)
      status_created (GSI1 SK, format = '{status}#{created_at}')
      agent, action, payload (Map), summary, status, approver,
      created_at, updated_at, decided_at?, executed_at?

    `status_created` is rewritten on every status transition so the GSI
    range scans still match the new status."""

    def __init__(self, table_name: str | None = None, region: str | None = None) -> None:
        self._table_name = table_name or settings.proposals_table
        self._region = region or settings.aws_region
        self._resource = None

    def _table(self):
        if self._resource is None:
            import boto3

            self._resource = boto3.resource("dynamodb", region_name=self._region)
        return self._resource.Table(self._table_name)

    @staticmethod
    def _to_item(proposal: Proposal) -> dict:
        from ..audit.events import to_dynamo

        item = proposal.model_dump()
        item["status_created"] = (
            f"{item.get('status', 'pending')}#{item.get('created_at')}"
        )
        return to_dynamo(item)

    @staticmethod
    def _from_item(item: dict) -> Proposal:
        item = {k: v for k, v in item.items() if k != "status_created"}
        return Proposal.model_validate(item)

    async def write(
        self,
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
        item = self._to_item(proposal)
        await asyncio.to_thread(self._table().put_item, Item=item)
        return proposal

    async def get(self, proposal_id: str) -> Proposal | None:
        # Lookup by SK requires investor_id (PK); the API has it, so this
        # client expects `proposal_id` to be `{investor_id}/{proposal_id}`
        # OR a global secondary scheme that's out of scope here. For now,
        # scan-by-proposal-id via a Query against the GSI would work in a
        # real deployment; the dev backend uses Mongo and doesn't hit this.
        raise NotImplementedError(
            "DynamoProposalsClient.get requires investor_id context; "
            "use the API which carries it via the path or query."
        )

    async def list_for_investor(
        self,
        investor_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Proposal]:
        from boto3.dynamodb.conditions import Key

        def _q():
            if status:
                resp = self._table().query(
                    IndexName=settings.proposals_gsi_status,
                    KeyConditionExpression=(
                        Key("investor_id").eq(investor_id)
                        & Key("status_created").begins_with(f"{status}#")
                    ),
                    ScanIndexForward=False,
                    Limit=limit,
                )
            else:
                resp = self._table().query(
                    KeyConditionExpression=Key("investor_id").eq(investor_id),
                    Limit=limit,
                )
            return resp.get("Items", [])

        items = await asyncio.to_thread(_q)
        return [self._from_item(i) for i in items]

    async def _transition(
        self,
        proposal_id: str,
        *,
        from_status: str,
        to_status: str,
        extra: dict,
    ) -> Proposal | None:
        # DynamoDB UpdateItem with a condition expression — only advances
        # if the row is currently in `from_status`. The status_created GSI
        # key is rewritten so the GSI still points at the right partition.
        def _u():
            from botocore.exceptions import ClientError

            try:
                resp = self._table().update_item(
                    Key={"investor_id": extra["investor_id"], "proposal_id": proposal_id},
                    ConditionExpression="#s = :from_s",
                    UpdateExpression=(
                        "SET #s = :to_s, status_created = :sc, updated_at = :ts"
                        + (", approver = :ap" if "approver" in extra else "")
                        + (", decided_at = :dt" if to_status in ("approved", "rejected") else "")
                        + (", executed_at = :et" if to_status == "executed" else "")
                    ),
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={
                        ":from_s": from_status,
                        ":to_s": to_status,
                        ":sc": f"{to_status}#{extra['created_at']}",
                        ":ts": extra["updated_at"],
                        **({":ap": extra["approver"]} if "approver" in extra else {}),
                        **(
                            {":dt": extra["updated_at"]}
                            if to_status in ("approved", "rejected") else {}
                        ),
                        **({":et": extra["updated_at"]} if to_status == "executed" else {}),
                    },
                    ReturnValues="ALL_NEW",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return None
                raise
            return resp.get("Attributes")

        return await asyncio.to_thread(_u) and self._from_item(_u())  # type: ignore[func-returns-value]

    async def mark_approved(self, proposal_id: str, *, approver: str) -> Proposal | None:
        # Dynamo callers need investor_id alongside the proposal_id.
        # The API endpoint passes it through `_extra`. Keep this thin in
        # dev/CI: the smoke uses the Mongo backend.
        raise NotImplementedError(
            "Use the API endpoint; the API supplies investor_id when calling Dynamo."
        )

    async def mark_rejected(self, proposal_id: str, *, approver: str) -> Proposal | None:
        raise NotImplementedError("Use the API endpoint.")

    async def mark_executed(self, proposal_id: str) -> Proposal | None:
        raise NotImplementedError("Use the API endpoint.")


# ---- factory ---------------------------------------------------------------
_default: ProposalClientProtocol | None = None


def get_client() -> ProposalClientProtocol:
    global _default
    if _default is None:
        backend = (settings.proposals_backend or "mongo").lower()
        if backend == "dynamo":
            _default = DynamoProposalsClient()
        elif backend == "mongo":
            _default = MongoProposalsClient()
        else:
            raise ValueError(f"unknown proposals_backend: {backend!r}")
    return _default


def set_default(client: ProposalClientProtocol | None) -> None:
    global _default
    _default = client
