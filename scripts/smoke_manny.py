"""Step-10 smoke: Manny — work orders + vendor dispatch.

Drives the gated path:
  - Manny lists plumbing vendors → picks one → calls dispatch_vendor.
  - Runner intercepts; proposal queued with the full work_order payload.
  - API approve → execution looks up the vendor, validates trade match,
    'sends' (mocked), writes a work_order artifact.

Negative paths:
  - Dispatching a vendor whose roster doesn't list the trade raises a
    clear execution error and leaves the proposal in `approved`.
  - Dispatching an inactive vendor likewise fails."""
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
from reeve.models import Building, Investor, Portfolio, Unit, UnitStatus
from reeve.models.stubs import Vendor
from reeve.repos.investors import upsert_investor
from reeve.repos.vendors import upsert_vendor
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


async def _seed() -> dict:
    investor = Investor(name="James M.", entity_name="Oakwood Holdings")
    await upsert_investor(investor)
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    building = Building(portfolio_id=portfolio.id, address="412 Lincoln St", units_count=4)
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    units = []
    for i in range(4):
        u = Unit(building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                 market_rent=1466, status=UnitStatus.OCCUPIED)
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
        units.append(u)
    plumber = Vendor(
        investor_id=investor.id, name="ACME Plumbing",
        trades=["plumbing"], contact_email="dispatch@acmeplumbing.com",
        contact_phone="+1-201-555-0123", rates={"plumbing": 145.0},
    )
    await upsert_vendor(plumber)
    electrician = Vendor(
        investor_id=investor.id, name="Bright Electric",
        trades=["electrical"], contact_email="ops@brightelectric.com",
        rates={"electrical": 160.0},
    )
    await upsert_vendor(electrician)
    inactive = Vendor(
        investor_id=investor.id, name="Old Vendor",
        trades=["hvac"], contact_email="contact@old.com", active=False,
    )
    await upsert_vendor(inactive)
    return {
        "investor": investor, "building": building, "units": units,
        "plumber": plumber, "electrician": electrician, "inactive": inactive,
    }


async def main() -> None:
    print("step-10 smoke (Manny — work orders):")
    install_mock_db()
    audit = install_mock_audit()
    s = await _seed()
    investor, building = s["investor"], s["building"]
    plumber = s["plumber"]
    unit_2b = next(u for u in s["units"] if u.label == "2B")

    # ---- Happy path: dispatch the plumber ----------------------------------
    dispatch_payload = {
        "vendor_id": plumber.id,
        "building_id": building.id,
        "unit_id": unit_2b.id,
        "trade": "plumbing",
        "scope": "Unit 2B kitchen sink leaking under the cabinet — diagnose and repair.",
        "priority": "urgent",
        "max_spend": 500.0,
    }
    scripted = [
        _Resp([_Block("tool_use", id="m1", name="list_vendors_by_trade",
                      input={"trade": "plumbing"})]),
        _Resp([_Block("tool_use", id="m2", name="dispatch_vendor",
                      input=dispatch_payload)]),
        _Resp([_Block("text", text="ACME Plumbing dispatched at urgent. Cap $500.")]),
    ]
    import reeve.llm as llm_mod
    llm_mod.set_async_client(_FakeAnthropic(scripted))

    manny = load_agent("manny")
    assert manny.gated_actions == ["dispatch_vendor"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(manny, "Plumbing leak at 412 Lincoln Unit 2B.", ctx)

    assert result.status == "gated" and len(result.proposal_ids) == 1
    pid = result.proposal_ids[0]
    print(f"  manny: tools={result.tools_called}, proposal queued={pid[:8]}…")

    # ---- API approve + execute ----------------------------------------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    from reeve.api.auth import issue_token
    headers = {"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"}
    with TestClient(app) as client:
        client.headers.update(headers)
        r = client.post(f"/api/proposals/{pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is True
        wo_artifact_id = body["result"]["artifact_id"]
        assert body["result"]["vendor_name"] == "ACME Plumbing"
        print(f"  approve+execute: vendor={body['result']['vendor_name']}, "
              f"artifact_id={wo_artifact_id[:8]}…")

    # Artifact validates and carries the dispatched_at + contact.
    schema = json.loads(Path("contracts/work_order.schema.json").read_text())
    art = await mongo_module.db()["artifacts"].find_one({"_id": wo_artifact_id})
    jsonschema.Draft7Validator(schema).validate(art["payload"])
    assert art["payload"]["trade"] == "plumbing"
    assert art["payload"]["dispatched_at"]
    assert art["payload"]["contact"]["email"] == "dispatch@acmeplumbing.com"
    print(f"  artifact: type={art['type']}, trade={art['payload']['trade']}, validates ✓")

    # ---- Negative: dispatch a vendor whose trades don't include 'hvac' ------
    install_mock_audit()
    bad_payload = {**dispatch_payload, "trade": "hvac"}
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="m1", name="dispatch_vendor", input=bad_payload)]),
        _Resp([_Block("text", text="Queued.")]),
    ]))
    bad = await run_agent(manny, "Dispatch", ctx)
    bad_pid = bad.proposal_ids[0]
    with TestClient(app) as client:
        client.headers.update(headers)
        r = client.post(f"/api/proposals/{bad_pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is False
        assert "trade" in body["error"].lower()
        assert body["proposal"]["status"] == "approved"
    print(f"  trade-mismatch: execution refused, proposal stays approved (retry-able)")

    # ---- Negative: inactive vendor ------------------------------------------
    install_mock_audit()
    inactive = s["inactive"]
    inactive_payload = {**dispatch_payload, "vendor_id": inactive.id, "trade": "hvac"}
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="m1", name="dispatch_vendor", input=inactive_payload)]),
        _Resp([_Block("text", text="Queued.")]),
    ]))
    bad2 = await run_agent(manny, "Dispatch", ctx)
    bad2_pid = bad2.proposal_ids[0]
    with TestClient(app) as client:
        client.headers.update(headers)
        r = client.post(f"/api/proposals/{bad2_pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is False
        assert "inactive" in body["error"].lower()
    print(f"  inactive-vendor: execution refused")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
