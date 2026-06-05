"""Step-11 smoke: Leo — leasing.

Drives the gated post_listing flow:
  - list_vacant_units returns the vacant Unit 4B.
  - pull_comps returns the area's market rent.
  - post_listing is intercepted; proposal queued with the listing
    payload.
  - API approve fires the handler: 'posts' to each channel (mocked,
    generates URLs), writes a listing artifact with posted_at + URLs.

Negative path:
  - Trying to list an OCCUPIED unit surfaces a clear execution error."""
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
from reeve.repos.investors import upsert_investor
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
    building = Building(
        portfolio_id=portfolio.id,
        address="412 Lincoln St, Westfield, NJ 07090",
        units_count=4,
    )
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    units = []
    for i in range(4):
        u = Unit(
            building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
            market_rent=1466,
            status=UnitStatus.OCCUPIED if i < 3 else UnitStatus.VACANT,
        )
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
        units.append(u)
    return {"investor": investor, "building": building, "units": units}


async def main() -> None:
    print("step-11 smoke (Leo — leasing):")
    install_mock_db()
    audit = install_mock_audit()
    s = await _seed()
    investor, building = s["investor"], s["building"]
    vacant = next(u for u in s["units"] if u.status == "vacant")
    occupied = next(u for u in s["units"] if u.status == "occupied")

    listing_payload = {
        "unit_id": vacant.id,
        "building_id": building.id,
        "asking_rent": 1475.0,
        "deposit": 1475.0,
        "term_months": 12,
        "available_from": "2026-07-01",
        "headline": f"2BR Westfield walk-up — hardwood, parking · Unit {vacant.label}",
        "description": (
            f"Refreshed 2BR in {building.address}. Hardwood floors, in-unit "
            "laundry, off-street parking. Walking distance to NJ Transit. "
            "Available July 1."
        ),
        "amenities": ["hardwood floors", "in-unit laundry", "parking"],
        "channels": ["zillow", "apartments_com"],
    }
    scripted = [
        _Resp([_Block("tool_use", id="l1", name="list_vacant_units", input={})]),
        _Resp([_Block("tool_use", id="l2", name="pull_comps",
                      input={"address": building.address})]),
        _Resp([_Block("tool_use", id="l3", name="post_listing", input=listing_payload)]),
        _Resp([_Block("text", text=f"Unit {vacant.label} listed at $1,475 across Zillow + Apartments.com.")]),
    ]
    import reeve.runtime.runner as runner_module
    runner_module._client_singleton = _FakeAnthropic(scripted)

    leo = load_agent("leo")
    assert leo.gated_actions == ["post_listing"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(leo, "List the vacant unit at 412 Lincoln.", ctx)

    assert result.status == "gated" and len(result.proposal_ids) == 1
    pid = result.proposal_ids[0]
    print(f"  leo: tools={result.tools_called}, proposal queued={pid[:8]}…")

    # Sensitive read on `lease` (list_vacant_units back-fills last lease).
    sens = [
        e for e in audit.events
        if e.get("kind") == "read" and (e.get("detail") or {}).get("scope") == "lease"
    ]
    assert sens, "expected a sensitive-read audit on `lease`"
    print(f"  sensitive-read audit: {len(sens)} on `lease`")

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
        assert set(body["result"]["channels"]) == {"zillow", "apartments_com"}
        assert "zillow" in body["result"]["listing_urls"]
        artifact_id = body["result"]["artifact_id"]
        print(
            f"  approve+execute: posted to {sorted(body['result']['channels'])}, "
            f"first url={list(body['result']['listing_urls'].values())[0][:60]}…"
        )

    schema = json.loads(Path("contracts/listing.schema.json").read_text())
    art = await mongo_module.db()["artifacts"].find_one({"_id": artifact_id})
    jsonschema.Draft7Validator(schema).validate(art["payload"])
    assert art["payload"]["asking_rent"] == 1475.0
    assert art["payload"]["posted_at"]
    assert "zillow" in art["payload"]["listing_urls"]
    print(f"  artifact: type={art['type']}, validates ✓")

    # ---- Negative: listing an OCCUPIED unit must fail at exec --------------
    install_mock_audit()
    bad_payload = {**listing_payload, "unit_id": occupied.id}
    runner_module._client_singleton = _FakeAnthropic([
        _Resp([_Block("tool_use", id="l1", name="post_listing", input=bad_payload)]),
        _Resp([_Block("text", text="Queued.")]),
    ])
    bad = await run_agent(leo, "List the occupied unit.", ctx)
    bad_pid = bad.proposal_ids[0]
    with TestClient(app) as client:
        client.headers.update(headers)
        r = client.post(f"/api/proposals/{bad_pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is False
        assert "occupied" in body["error"] or "not vacant" in body["error"]
        assert body["proposal"]["status"] == "approved"
    print(f"  occupied-unit: execution refused, proposal stays approved (retry-able)")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
