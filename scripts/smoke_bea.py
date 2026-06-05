"""Step-8 smoke: Bea — bookkeeping.

Drives Bea against an already-synced ledger (Reed's seed flow):
  - Recategorizes a row the rule-based pass mislabelled (`other` → real).
  - Proposes an adjusting entry → runner intercepts, queues proposal.
  - Submits the bookkeeping_report artifact.

Then drives the proposal through the API approve endpoint:
  - The execution layer runs post_adjusting_entry, which writes a NEW
    Transaction with reconciled=true, categorized_by=bea, marked
    [Adjustment] in the description.
  - The new row carries the right investor_id (looked up from the
    building → portfolio chain at execution time)."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

import jsonschema
from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.finance.plaid import MockPlaidClient, sync_transactions
from reeve.finance.seed import synthesize_transactions
from reeve.models import (
    Building,
    BuyBox,
    Investor,
    Portfolio,
    Unit,
    UnitStatus,
)
from reeve.repos.investors import upsert_investor
from reeve.repos.transactions import list_transactions as repo_list
from reeve.runtime import RunContext, load_agent, run_agent


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    proposals_mod.set_default(None)
    return client


class _InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kw: Any) -> Any:
        from reeve.audit import AuditEvent
        ev = AuditEvent(**kw)
        self.events.append(ev.model_dump())
        return ev

    def write(self, event: Any) -> Any:
        self.events.append(event.model_dump() if hasattr(event, "model_dump") else event)
        return event

    def feed(self, *a: Any, **k: Any) -> list[dict]:
        return list(self.events)

    def by_entity(self, *a: Any, **k: Any) -> list[dict]:
        return []


def install_mock_audit() -> _InMemoryAudit:
    sink = _InMemoryAudit()
    audit_mod.set_default(sink)
    return sink


@dataclass
class _Block:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict | None = None


@dataclass
class _Resp:
    content: list[_Block]


class _FakeAnthropic:
    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.messages = self

    async def create(self, **kw: Any) -> _Resp:
        return self._scripted.pop(0)


async def _seed() -> tuple[Investor, Building]:
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20),
    )
    await upsert_investor(investor)
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    building = Building(portfolio_id=portfolio.id, address="27 South Ave", units_count=6)
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    for i in range(6):
        u = Unit(building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                 market_rent=1466, status=UnitStatus.OCCUPIED)
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))

    # Sync 30 days of fixtures so Bea has something to chew on.
    fixtures = synthesize_transactions(
        building_id=building.id, units=building.units_count,
        market_rent=1466.0, days=30, seed=4242,
    )
    # Inject a deliberately-ambiguous transaction the rule-based categorizer
    # is bound to mark `other` — Bea's job to fix.
    fixtures.append({
        "plaid_id": f"misc-{building.id}-2026-05-22",
        "account_id": f"acct-{building.id}",
        "date": "2026-05-22",
        "amount": -185.0,
        "description": "Boiler service call",  # no keyword the rule list catches
        "merchant": "Northeast Boiler Co",
        "plaid_category": ["Service"],
    })
    client = MockPlaidClient(fixtures=fixtures)
    ptxns = client.fetch_transactions(f"acct-{building.id}", "1970-01-01", "9999-12-31")
    await sync_transactions(
        investor_id=investor.id, building_id=building.id, plaid_txns=ptxns,
    )
    return investor, building


async def main() -> None:
    print("step-8 smoke (Bea — bookkeeping):")
    install_mock_db()
    audit = install_mock_audit()
    investor, building = await _seed()

    # Find the "other" rows the rule-based pass mislabelled.
    all_txns = await repo_list(
        investor_id=investor.id, period_start="1970-01-01", period_end="9999-12-31",
    )
    others = [t for t in all_txns if t.get("category") == "other"]
    assert others, "expected at least one 'other' row to fix"
    target = others[0]
    target_id = target["_id"]
    print(f"  seed: {len(all_txns)} txns, {len(others)} marked 'other' (target: {target['description']!r})")

    # ---- script Bea's run --------------------------------------------------
    bookkeeping_payload = {
        "type": "bookkeeping_report",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "period": {"start": "2026-05-01", "end": "2026-05-31"},
        "reviewed": len(all_txns),
        "recategorized": 1,
        "adjusting_entries_proposed": 1,
        "category_distribution": {},  # left empty; the LLM would fill in
        "anomalies": [
            {"kind": "uncategorized", "severity": "watch",
             "text": f"Boiler service call lacked a matching rule pattern — recategorized to maintenance.",
             "transaction_id": target_id, "amount": target["amount"],
             "building_id": building.id},
        ],
        "thesis": "Books are clean except one rule-misser; proposed a small reclassification adjustment.",
        "confidence": "high",
        "unverified": [],
    }
    scripted = [
        _Resp([_Block("tool_use", id="b1", name="list_transactions",
                      input={"period_start": "2026-05-01", "period_end": "2026-05-31"})]),
        _Resp([_Block("tool_use", id="b2", name="update_transaction_category",
                      input={"transaction_id": target_id, "category": "maintenance",
                             "reason": "Boiler service is a maintenance expense; "
                                       "rule list lacks the term."})]),
        _Resp([_Block("tool_use", id="b3", name="post_adjusting_entry",
                      input={"building_id": building.id,
                             "date": "2026-05-22",
                             "amount": -45.0, "category": "maintenance",
                             "description": "Service-call surcharge invoiced after the fact",
                             "reason": "Surcharge invoice arrived post-period; books need balance."})]),
        _Resp([
            _Block("text", text="Recategorized 1 row, proposed 1 adjustment."),
            _Block("tool_use", id="b4", name="submit_bookkeeping_report",
                   input={"artifact": bookkeeping_payload}),
        ]),
    ]
    import reeve.runtime.runner as runner_module
    runner_module._client_singleton = _FakeAnthropic(scripted)

    bea = load_agent("bea")
    assert bea.id == "bea" and bea.gated_actions == ["post_adjusting_entry"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(bea, "Clean up May 2026.", ctx)

    assert result.artifact is not None and result.artifact["type"] == "bookkeeping_report"
    schema = json.loads(Path("contracts/bookkeeping_report.schema.json").read_text())
    contract_only = {k: v for k, v in result.artifact.items()
                     if k not in ("artifact_id", "version", "supersedes")}
    jsonschema.Draft7Validator(schema).validate(contract_only)
    assert len(result.proposal_ids) == 1
    print(f"  bea: tools={result.tools_called}, "
          f"proposal queued={result.proposal_ids[0][:8]}…")

    # The target row was updated in place (inline ACT_INTERNAL).
    updated = await mongo_module.db()["transactions"].find_one({"_id": target_id})
    assert updated["category"] == "maintenance"
    assert updated["categorized_by"] == "bea"
    assert updated["categorized_at"]
    print(f"  recategorized: {target_id[:8]}… → maintenance (categorized_by=bea)")

    # The adjusting entry stays unposted until the API approves it.
    before_count = await mongo_module.db()["transactions"].count_documents({})
    print(f"  pre-approval txn count: {before_count} (no adjustment posted yet)")

    # ---- API approve → execution writes the adjustment row -----------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    proposal_id = result.proposal_ids[0]
    from reeve.api.auth import issue_token
    with TestClient(app) as client:
        client.headers.update({"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"})
        r = client.get(f"/api/proposals/{proposal_id}")
        assert r.status_code == 200 and r.json()["action"] == "post_adjusting_entry"

        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            json={"approver": "james"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is True
        new_txn_id = body["result"]["transaction_id"]
        print(f"  approve+execute: new ledger row {new_txn_id[:8]}… posted")

    # The new row landed and carries the right investor_id / Bea metadata.
    after_count = await mongo_module.db()["transactions"].count_documents({})
    assert after_count == before_count + 1
    new_row = await mongo_module.db()["transactions"].find_one({"_id": new_txn_id})
    assert new_row["investor_id"] == investor.id
    assert new_row["building_id"] == building.id
    assert new_row["category"] == "maintenance"
    assert new_row["categorized_by"] == "bea"
    assert new_row["reconciled"] is True
    assert "[Adjustment]" in new_row["description"]
    print(f"  adjustment row: investor={new_row['investor_id'][:8]}…, "
          f"category={new_row['category']}, reconciled={new_row['reconciled']}")

    # Audit chain.
    kinds = [e.get("kind") for e in audit.events]
    counts = {k: kinds.count(k) for k in set(kinds)}
    assert counts.get("read", 0) >= 1, counts          # list_transactions
    assert counts.get("act_internal", 0) >= 2, counts  # update + submit
    assert counts.get("proposed", 0) == 1, counts
    assert counts.get("approved", 0) == 1, counts
    assert counts.get("executed", 0) == 1, counts
    assert counts.get("artifact", 0) == 1, counts
    print(f"  audit: {len(audit.events)} events, {counts}")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
