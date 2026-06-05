"""Smoke for Reeve's add_property tool.

Verifies:
  - First call on an investor with no portfolio creates a default
    "Main Portfolio", a building under it, and N units with the
    auto-generated 1A/1B/2A/2B pattern.
  - Second call reuses the existing portfolio (no new one created).
  - Custom `unit_labels` override the auto-generated pattern (length-
    matched).
  - `units_per_floor=3` produces 1A 1B 1C 2A 2B 2C.
  - Adding the same address twice refuses (added=False) with a
    deduplication message.
  - The GET /api/portfolio endpoint reflects the new structure.
  - Audit captures act_internal on every add_property call.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.llm as llm_mod
import reeve.proposals as proposals_mod
from reeve.models import BuyBox, Investor
from reeve.repos.buildings import list_buildings_in_portfolios
from reeve.repos.investors import upsert_investor
from reeve.repos.portfolios import list_portfolios
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

    def write(self, e: Any) -> Any:
        self.events.append(e.model_dump() if hasattr(e, "model_dump") else e)
        return e

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


async def _drive_reeve(investor_id: str, tool_input: dict) -> dict:
    """Run Reeve once with a single add_property tool call. Returns the
    tool result dict (which the LLM echoes back in its text response)."""
    scripted = [
        _Resp([_Block("tool_use", id="r1", name="add_property", input=tool_input)]),
        _Resp([_Block("text", text="Added.")]),
    ]
    llm_mod.set_async_client(_FakeAnthropic(scripted))
    reeve = load_agent("reeve")
    ctx = RunContext(investor_id=investor_id, conversation_id="c1")
    await run_agent(reeve, "Add a property.", ctx)
    # The tool result is in Mongo + the audit; we'll inspect there.
    return {}


async def main() -> None:
    print("smoke_add_property:")
    install_mock_db()
    audit = install_mock_audit()

    investor = Investor(
        name="Jake Test", entity_name="Test Holdings",
        buy_box=BuyBox(cap_floor=0.075, min_dscr=1.20),
    )
    await upsert_investor(investor)

    # Investor starts with zero portfolios.
    assert (await list_portfolios(investor.id)) == []
    print(f"  seed: investor {investor.id[:8]}… has no portfolio")

    # ---- 1) First add: default labels (2/floor), default portfolio name --
    await _drive_reeve(investor.id, {
        "address": "412 Lincoln St, Westfield, NJ",
        "units_count": 4,
        "basis": 720000,
        "acquired_at": "2024-01-01",
        "financing": {"rate": 0.0675, "term": 25, "ltv": 0.70},
        "market_rent": 1466,
    })
    portfolios = await list_portfolios(investor.id)
    assert len(portfolios) == 1, portfolios
    assert portfolios[0].name == "Main Portfolio"
    p_id = portfolios[0].id
    buildings = await list_buildings_in_portfolios([p_id])
    assert len(buildings) == 1
    b = buildings[0]
    assert b.address == "412 Lincoln St, Westfield, NJ"
    assert b.units_count == 4
    assert b.basis == 720000
    assert b.financing.rate == 0.0675
    units = await mongo_module.db()["units"].find({"building_id": b.id}).to_list(length=10)
    labels = sorted([u["label"] for u in units])
    assert labels == ["1A", "1B", "2A", "2B"], labels
    assert units[0]["market_rent"] == 1466
    print(f"  add #1: portfolio created ('Main Portfolio'), building, "
          f"units={labels}")

    # ---- 2) Second add: same investor, different address, no new portfolio
    await _drive_reeve(investor.id, {
        "address": "88 Springfield Ave, Summit, NJ",
        "units_count": 6,
        "units_per_floor": 3,
        "basis": 2_150_000,
    })
    portfolios = await list_portfolios(investor.id)
    assert len(portfolios) == 1, "should reuse existing portfolio"
    buildings = await list_buildings_in_portfolios([p_id])
    assert len(buildings) == 2
    second = next(b for b in buildings if b.address.startswith("88"))
    second_units = await mongo_module.db()["units"].find(
        {"building_id": second.id}
    ).to_list(length=10)
    second_labels = sorted([u["label"] for u in second_units])
    assert second_labels == ["1A", "1B", "1C", "2A", "2B", "2C"], second_labels
    print(f"  add #2: portfolio REUSED, second building, units_per_floor=3 → {second_labels}")

    # ---- 3) Custom unit labels --------------------------------------------
    await _drive_reeve(investor.id, {
        "address": "1423 Elmwood Ave, Westfield, NJ",
        "units_count": 3,
        "unit_labels": ["Studio-1", "Studio-2", "Loft"],
    })
    elmwood = await mongo_module.db()["buildings"].find_one(
        {"address": "1423 Elmwood Ave, Westfield, NJ"}
    )
    elm_units = await mongo_module.db()["units"].find(
        {"building_id": elmwood["_id"]}
    ).to_list(length=10)
    elm_labels = sorted([u["label"] for u in elm_units])
    assert elm_labels == ["Loft", "Studio-1", "Studio-2"], elm_labels
    print(f"  add #3: custom labels honored → {elm_labels}")

    # ---- 4) Duplicate address refuses --------------------------------------
    # Drive Reeve through a 4th add_property on an existing address. The
    # tool result will carry `added=False`; the runner records the call
    # but no new building lands.
    pre_count = await mongo_module.db()["buildings"].count_documents({})
    await _drive_reeve(investor.id, {
        "address": "412 Lincoln St, Westfield, NJ",  # already exists
        "units_count": 4,
    })
    post_count = await mongo_module.db()["buildings"].count_documents({})
    assert post_count == pre_count, (pre_count, post_count)
    print(f"  add #4: duplicate address refused (buildings stayed at {post_count})")

    # ---- 5) /api/portfolio reflects the new structure ----------------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app
    from reeve.api.auth import issue_token

    app = build_app()
    with TestClient(app) as client:
        client.headers.update({"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"})
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["buildings"] == 3
        assert body["totals"]["units"] == 4 + 6 + 3
        names = [p["name"] for p in body["portfolios"]]
        assert names == ["Main Portfolio"], names
        print(f"  /api/portfolio: buildings={body['totals']['buildings']}, "
              f"units={body['totals']['units']}, portfolios={names}")

    # ---- 6) Audit chain ----------------------------------------------------
    act_internal = [e for e in audit.events
                    if e.get("kind") == "act_internal"
                    and (e.get("detail") or {}).get("tool") == "add_property"]
    assert len(act_internal) == 4, len(act_internal)
    print(f"  audit: {len(act_internal)} act_internal events on add_property")

    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
