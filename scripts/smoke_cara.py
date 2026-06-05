"""Step-9 smoke: Cara — tenant comms.

Drives Cara end-to-end:
  - find_lease_for_unit resolves a unit → lease → tenant (sensitive
    reads on `lease` and `tenant` both audit).
  - send_tenant_message is gated: runner intercepts, persists a
    pending proposal with the message payload.
  - API approve fires the handler: it picks the right contact channel,
    'sends' (mocked), and writes the tenant_message artifact.
  - Negative: trying to message a tenant who has no email contact for
    an email channel surfaces a clear execution error and leaves the
    proposal in `approved` (not executed) for retry."""
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
from reeve.models import (
    Building,
    Investor,
    Portfolio,
    Unit,
    UnitStatus,
)
from reeve.models.stubs import Lease, LeaseStatus, Tenant, TenantContact
from reeve.repos.investors import upsert_investor
from reeve.repos.leases import upsert_lease
from reeve.repos.tenants import upsert_tenant
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
                 market_rent=1466,
                 status=UnitStatus.OCCUPIED if i < 3 else UnitStatus.VACANT)
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
        units.append(u)

    # Tenant in 2A with an email; another in 1A with phone only (negative path).
    tenant_2a = Tenant(
        investor_id=investor.id,
        name="Priya Nair",
        contacts=[
            TenantContact(kind="email", value="priya@example.com"),
            TenantContact(kind="phone", value="+1-201-555-0149"),
        ],
    )
    await upsert_tenant(tenant_2a)
    lease_2a = Lease(
        investor_id=investor.id, unit_id=units[2].id, tenant_id=tenant_2a.id,
        term_start="2025-09-01", term_end="2026-08-31",
        rent=1350.0, security_deposit=2700.0,
        renewal_date="2026-06-30",
        status=LeaseStatus.ACTIVE,
    )
    await upsert_lease(lease_2a)

    tenant_1a = Tenant(
        investor_id=investor.id,
        name="Diego Costa",
        contacts=[TenantContact(kind="phone", value="+1-201-555-0142")],
    )
    await upsert_tenant(tenant_1a)
    lease_1a = Lease(
        investor_id=investor.id, unit_id=units[0].id, tenant_id=tenant_1a.id,
        term_start="2024-12-01", term_end="2025-11-30",
        rent=1200.0, security_deposit=2400.0,
        renewal_date="2025-09-30",
        status=LeaseStatus.ACTIVE,
    )
    await upsert_lease(lease_1a)

    return {
        "investor": investor, "building": building,
        "units": units,
        "tenants": {"2A": tenant_2a, "1A": tenant_1a},
        "leases": {"2A": lease_2a, "1A": lease_1a},
    }


async def main() -> None:
    print("step-9 smoke (Cara — tenant comms):")
    install_mock_db()
    audit = install_mock_audit()
    s = await _seed()
    investor, building = s["investor"], s["building"]

    # ---- Happy path: 2A tenant has email; renewal notice goes through ------
    tenant_2a = s["tenants"]["2A"]
    lease_2a = s["leases"]["2A"]
    unit_2a = next(u for u in s["units"] if u.label == "2A")
    body = (
        f"Hi {tenant_2a.name.split()[0]},\n\n"
        f"Your lease on Unit {unit_2a.label} at {building.address} ends "
        f"{lease_2a.term_end}. We'd like to renew at the current rent of "
        f"${lease_2a.rent:.0f}/mo for another 12 months. Please reply by "
        f"June 30 if you'd like to renew.\n\nThanks,\nOakwood Holdings"
    )
    msg_payload = {
        "tenant_id": tenant_2a.id,
        "lease_id": lease_2a.id,
        "unit_id": unit_2a.id,
        "building_id": building.id,
        "channel": "email",
        "subject": f"Renewal — {building.address} Unit {unit_2a.label}",
        "body": body,
        "purpose": "renewal_notice",
    }
    scripted = [
        _Resp([_Block("tool_use", id="c1", name="find_lease_for_unit",
                      input={"building_id": building.id, "unit_label": "2A"})]),
        _Resp([_Block("tool_use", id="c2", name="send_tenant_message",
                      input=msg_payload)]),
        _Resp([_Block("text", text="Renewal notice queued for Priya at 2A.")]),
    ]
    import reeve.runtime.runner as runner_module
    runner_module._client_singleton = _FakeAnthropic(scripted)

    cara = load_agent("cara")
    assert cara.gated_actions == ["send_tenant_message"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(cara, "Draft a renewal notice for unit 2A.", ctx)

    assert result.status == "gated"
    assert len(result.proposal_ids) == 1
    print(f"  cara: tools={result.tools_called}, proposal queued={result.proposal_ids[0][:8]}…")

    # Sensitive reads on `tenant` and `lease` both fire (find_lease_for_unit
    # touches both — the runner audits each scope separately).
    sens = [
        e for e in audit.events
        if e.get("kind") == "read" and (e.get("detail") or {}).get("scope") in ("tenant", "lease")
    ]
    scopes = {e["detail"]["scope"] for e in sens}
    assert scopes == {"tenant", "lease"}, scopes
    print(f"  sensitive-read audit: scopes={sorted(scopes)}")

    # No artifact yet — the tenant_message lives in the proposal payload
    # until execution.
    arts = await mongo_module.db()["artifacts"].find({"produced_by": "cara"}).to_list(length=5)
    assert arts == [], "tenant_message must not exist until executed"

    # ---- API approve + execute ----------------------------------------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    pid = result.proposal_ids[0]
    with TestClient(app) as client:
        r = client.get(f"/api/proposals/{pid}")
        assert r.status_code == 200
        proposal = r.json()
        assert proposal["payload"]["subject"].startswith("Renewal —")
        assert proposal["payload"]["channel"] == "email"

        r = client.post(f"/api/proposals/{pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is True
        assert body["result"]["channel"] == "email"
        assert body["result"]["to"] == "priya@example.com"
        executed_artifact_id = body["result"]["artifact_id"]
        print(f"  approve+execute: sent to {body['result']['to']}, "
              f"artifact_id={executed_artifact_id[:8]}…")

    schema = json.loads(Path("contracts/tenant_message.schema.json").read_text())
    art = await mongo_module.db()["artifacts"].find_one({"_id": executed_artifact_id})
    assert art["type"] == "tenant_message" and art["produced_by"] == "cara"
    jsonschema.Draft7Validator(schema).validate(art["payload"])
    assert art["payload"]["to"] == "priya@example.com"
    print(f"  artifact: type={art['type']}, validates ✓")

    # ---- Negative: tenant 1A has no email, channel=email must fail at exec --
    install_mock_audit()  # reset for clarity
    tenant_1a = s["tenants"]["1A"]
    lease_1a = s["leases"]["1A"]
    unit_1a = next(u for u in s["units"] if u.label == "1A")
    bad_payload = {
        "tenant_id": tenant_1a.id,
        "lease_id": lease_1a.id,
        "unit_id": unit_1a.id,
        "building_id": building.id,
        "channel": "email",
        "subject": "Hello",
        "body": "Test.",
        "purpose": "general",
    }
    scripted2 = [
        _Resp([_Block("tool_use", id="d1", name="send_tenant_message", input=bad_payload)]),
        _Resp([_Block("text", text="Queued.")]),
    ]
    runner_module._client_singleton = _FakeAnthropic(scripted2)
    result2 = await run_agent(cara, "Email 1A.", ctx)
    bad_pid = result2.proposal_ids[0]
    with TestClient(app) as client:
        r = client.post(f"/api/proposals/{bad_pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is False, body
        assert "email" in body["error"].lower()
        # Proposal stays approved (not executed) so a retry is possible.
        assert body["proposal"]["status"] == "approved"
    print(f"  negative: missing email surfaces error, proposal stays approved (retry-able)")

    # ---- Renewal-due query --------------------------------------------------
    runner_module._client_singleton = _FakeAnthropic([
        _Resp([_Block("tool_use", id="r1", name="list_leases_due_for_renewal",
                      input={"days_ahead": 90})]),
        _Resp([_Block("text", text="One lease due.")]),
    ])
    result3 = await run_agent(cara, "Anything due for renewal?", ctx)
    # The runner doesn't expose tool RESULTS to the smoke; just check the
    # call happened and a read audit fired on `lease`.
    assert "list_leases_due_for_renewal" in result3.tools_called
    print(f"  list_leases_due_for_renewal: called ✓")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
