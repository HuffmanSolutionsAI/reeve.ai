"""Step-6 smoke: Cole + Approvals.

Cole drafts → runtime intercepts the gated `send_loi` → proposal queued.
The API approve endpoint flips the proposal to `approved`, then the
execution layer (which is the ONLY thing that can run gated handlers)
fires the real `send_loi` handler. That writes the loi_draft artifact and
advances the deal to `under_contract`. Audit captures the full chain:
proposed → approved → executed."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

import jsonschema
from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.audit import AuditKind
from reeve.models import (
    Building,
    BuyBox,
    Deal,
    DealSource,
    DealStatus,
    Investor,
    Portfolio,
    Unit,
    UnitStatus,
)
from reeve.repos.deals import get_deal, upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.runtime import RunContext, load_agent, run_agent


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    # Reset the proposals client so it picks up the fresh Mongo handle.
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


async def _seed() -> tuple[Investor, Deal]:
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20, target_coc=0.08),
    )
    await upsert_investor(investor)
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    building = Building(portfolio_id=portfolio.id, address="1423 Elmwood Ave", units_count=8)
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    for i in range(8):
        u = Unit(building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                 market_rent=1466, status=UnitStatus.OCCUPIED)
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
    deal = Deal(
        investor_id=investor.id,
        address="1423 Elmwood Ave, Westfield, NJ 07090",
        units=8, ask=1_150_000, source=DealSource.MANUAL,
        status=DealStatus.PURSUE,
    )
    await upsert_deal(deal)
    return investor, deal


async def main() -> None:
    print("step-6 smoke (Cole + Approvals):")
    install_mock_db()
    audit = install_mock_audit()
    investor, deal = await _seed()

    # ---- Cole's run: pull_comps → send_loi (gated) ---------------------------
    loi_payload = {
        "deal_id": deal.id,
        "address": deal.address,
        "price": 1_060_000,
        "earnest_money": 26500,
        "due_diligence_days": 30,
        "financing_contingency_days": 45,
        "closing_days": 60,
        "addressee": {
            "name": "Maria Costa", "email": "maria@elmwoodrealty.com",
            "role": "Listing broker",
        },
        "terms": [
            "Price: $1,060,000",
            "Earnest money: $26,500 (2.5% of purchase price)",
            "Due diligence: 30 days from acceptance",
            "Financing contingency: 45 days",
            "Closing: 60 days from acceptance",
            "Subject to satisfactory inspection of rent roll and T-12",
        ],
        "narrative": "Anchoring at Ana's max-clearing price; terms protect the investor on diligence.",
    }
    scripted = [
        _Resp([_Block("tool_use", id="c1", name="pull_comps",
                      input={"address": deal.address})]),
        _Resp([_Block("tool_use", id="c2", name="send_loi",
                      input=loi_payload)]),
        _Resp([_Block("text", text="LOI queued at $1.06M, 2.5% EM, 30/45/60. Awaiting sign-off.")]),
    ]
    import reeve.llm as llm_mod
    llm_mod.set_async_client(_FakeAnthropic(scripted))

    cole = load_agent("cole")
    assert cole.id == "cole" and cole.gated_actions == ["send_loi"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(cole, "Draft an LOI for 1423 Elmwood at $1.06M.", ctx)

    assert result.status == "gated", f"expected gated, got {result.status!r}"
    assert len(result.proposal_ids) == 1
    assert result.artifact is None, "send_loi must not produce an artifact pre-approval"

    proposal_id = result.proposal_ids[0]
    print(f"  cole: tools={result.tools_called}, proposal queued={proposal_id[:8]}…, status={result.status}")

    # The deal stayed in `pursue` — the gate held; nothing advanced.
    d = await get_deal(deal.id)
    assert d and d.status == "pursue", f"deal moved pre-approval: {d.status if d else None!r}"

    # No artifact yet — the loi_draft is only persisted at execution time.
    arts = await mongo_module.db()["artifacts"].find({"deal_id": deal.id}).to_list(length=10)
    assert arts == [], "loi_draft must not exist until executed"

    # ---- API approve → execution layer fires send_loi ------------------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    from reeve.api.auth import issue_token
    with TestClient(app) as client:
        client.headers.update({"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"})
        r = client.get("/api/proposals?status=pending")
        assert r.status_code == 200, r.text
        pending = r.json()["proposals"]
        assert len(pending) == 1 and pending[0]["_id"] == proposal_id
        print(f"  /proposals?status=pending: {len(pending)} ({pending[0]['action']})")

        r = client.get(f"/api/proposals/{proposal_id}")
        assert r.status_code == 200 and r.json()["payload"]["price"] == 1_060_000

        r = client.post(
            f"/api/proposals/{proposal_id}/approve",
            json={"approver": "james"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is True
        assert body["proposal"]["status"] == "executed"
        result_payload = body["result"]
        assert result_payload["sent"] is True
        assert result_payload["deal_id"] == deal.id
        executed_artifact_id = result_payload["artifact_id"]
        print(f"  approve+execute: sent_at={result_payload['sent_at'][:19]}, "
              f"artifact_id={executed_artifact_id[:8]}…")

        # The deal advanced.
        r = client.get("/api/pipeline")
        counts = r.json()["counts"]
        assert counts.get("under_contract", 0) == 1, counts
        print(f"  /pipeline counts: {dict(counts)}")

        # The artifact landed and validates.
        r = client.get(f"/api/artifacts/{executed_artifact_id}")
        assert r.status_code == 200
        art = r.json()
        assert art["type"] == "loi_draft" and art["produced_by"] == "cole"
        schema = json.loads(Path("contracts/loi_draft.schema.json").read_text())
        jsonschema.Draft7Validator(schema).validate(art["payload"])
        print(f"  artifact: type={art['type']}, version={art['version']}, validates ✓")

        # Re-approving fails (proposal is no longer pending).
        r = client.post(f"/api/proposals/{proposal_id}/approve", json={"approver": "james"})
        assert r.status_code == 400
        print("  double-approve blocked (proposal not pending)")

    kinds = [e.get("kind") for e in audit.events]
    proposed = [e for e in audit.events if e.get("kind") == "proposed"]
    approved = [e for e in audit.events if e.get("kind") == "approved"]
    executed = [e for e in audit.events if e.get("kind") == "executed"]
    assert len(proposed) == 1 and len(approved) == 1 and len(executed) == 1
    print(f"  audit chain: proposed→approved→executed (events={len(audit.events)})")

    # ---- Reject path: a second proposal, this one rejected --------------------
    install_mock_audit()
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="d1", name="send_loi", input=loi_payload)]),
        _Resp([_Block("text", text="Queued.")]),
    ]))
    result2 = await run_agent(cole, "Queue another LOI.", ctx)
    pid2 = result2.proposal_ids[0]
    with TestClient(app) as client:
        client.headers.update({"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"})
        r = client.post(f"/api/proposals/{pid2}/reject", json={"approver": "james"})
        assert r.status_code == 200 and r.json()["proposal"]["status"] == "rejected"
    print(f"  reject path: proposal {pid2[:8]}… → rejected (no execution)")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
