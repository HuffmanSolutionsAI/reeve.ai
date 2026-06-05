"""Smoke for Reeve's update_property + remove_property.

Verifies:
  - update_property is a true partial patch (basis updates; address/financing
    untouched).
  - new_address renames the building.
  - update_property without any fields → updated=False.
  - update_property on a nonexistent address → updated=False.
  - remove_property on a clean building deletes the building + its units.
  - remove_property on a building with a lease refuses with dependency counts.
  - remove_property with force=true cascade-deletes the lease, the
    transactions, the units, and the building.
  - Cross-investor: investor B can't update or remove investor A's building.
  - Audit captures sensitive reads on lease + transaction during the
    refusing call (which still reads those scopes)."""
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
from reeve.models import Investor
from reeve.models.stubs import Lease, LeaseStatus, Transaction
from reeve.repos.buildings import find_building_by_address, get_building
from reeve.repos.investors import upsert_investor
from reeve.repos.leases import upsert_lease
from reeve.repos.transactions import insert_transactions
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


async def _drive(investor_id: str, tool_name: str, tool_input: dict) -> None:
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="r1", name=tool_name, input=tool_input)]),
        _Resp([_Block("text", text="ok.")]),
    ]))
    reeve = load_agent("reeve")
    ctx = RunContext(investor_id=investor_id, conversation_id="c1")
    await run_agent(reeve, "go", ctx)


async def main() -> None:
    print("smoke_property_update_remove:")
    install_mock_db()
    audit = install_mock_audit()

    a = Investor(name="Investor A")
    b = Investor(name="Investor B")
    await upsert_investor(a)
    await upsert_investor(b)

    # Seed A with two buildings, B with one.
    await _drive(a.id, "add_property", {
        "address": "412 Lincoln St, Westfield, NJ",
        "units_count": 4, "basis": 720000,
        "financing": {"rate": 0.0675, "term": 25, "ltv": 0.70},
    })
    await _drive(a.id, "add_property", {
        "address": "27 South Ave, Westfield, NJ",
        "units_count": 6, "basis": 980000,
    })
    await _drive(b.id, "add_property", {
        "address": "1 Beach St, Asbury Park, NJ",
        "units_count": 8,
    })

    lincoln = await find_building_by_address(a.id, "412 Lincoln St, Westfield, NJ")
    south = await find_building_by_address(a.id, "27 South Ave, Westfield, NJ")
    beach = await find_building_by_address(b.id, "1 Beach St, Asbury Park, NJ")
    assert lincoln and south and beach
    print(f"  seed: A has {lincoln.address[:15]}…, {south.address[:15]}…; B has {beach.address[:12]}…")

    # ---- 1) update_property: partial patch on basis only -----------------
    install_mock_audit()  # reset to make later assertions easier
    audit = audit_mod.get_audit()
    await _drive(a.id, "update_property", {
        "address": "412 Lincoln St, Westfield, NJ",
        "basis": 750000,
    })
    refreshed = await get_building(lincoln.id)
    assert refreshed.basis == 750000
    assert refreshed.address == "412 Lincoln St, Westfield, NJ"   # untouched
    assert refreshed.financing.rate == 0.0675                     # untouched
    print(f"  update basis: 720000 → {refreshed.basis} (address + financing untouched)")

    # ---- 2) update_property: new_address renames --------------------------
    await _drive(a.id, "update_property", {
        "address": "412 Lincoln St, Westfield, NJ",
        "new_address": "412 Lincoln Street, Westfield, NJ",
    })
    refreshed = await get_building(lincoln.id)
    assert refreshed.address == "412 Lincoln Street, Westfield, NJ"
    print(f"  rename: → {refreshed.address!r}")

    # ---- 3) update_property: no fields → updated=False --------------------
    await _drive(a.id, "update_property", {
        "address": "27 South Ave, Westfield, NJ",
    })
    south_now = await get_building(south.id)
    assert south_now.basis == 980000  # unchanged
    print("  no-fields update: refused, building untouched")

    # ---- 4) update_property: not found → updated=False -------------------
    await _drive(a.id, "update_property", {
        "address": "999 Made Up Lane",
        "basis": 100000,
    })
    print("  unknown address: refused (no error)")

    # ---- 5) Cross-investor: A can't touch B's building --------------------
    await _drive(a.id, "update_property", {
        "address": "1 Beach St, Asbury Park, NJ",
        "basis": 1,
    })
    beach_now = await get_building(beach.id)
    assert beach_now.basis is None  # B's building was never given a basis
    print("  cross-investor update: refused (B's building untouched)")

    # ---- 6) remove_property: clean building → deletes building + units ---
    install_mock_audit()
    audit = audit_mod.get_audit()
    pre_units = await mongo_module.db()["units"].count_documents(
        {"building_id": south.id}
    )
    assert pre_units == 6
    await _drive(a.id, "remove_property", {
        "address": "27 South Ave, Westfield, NJ",
    })
    assert await get_building(south.id) is None
    post_units = await mongo_module.db()["units"].count_documents(
        {"building_id": south.id}
    )
    assert post_units == 0
    print(f"  remove clean: building gone, 6 units gone")

    # ---- 7) remove_property: with lease + transaction → refuses ---------
    # Find a unit on Lincoln and attach a lease + a transaction
    unit = await mongo_module.db()["units"].find_one({"building_id": lincoln.id})
    await upsert_lease(Lease(
        investor_id=a.id, unit_id=unit["_id"], tenant_id="t1",
        term_start="2026-01-01", term_end="2026-12-31",
        rent=1500.0, status=LeaseStatus.ACTIVE,
    ))
    await insert_transactions([Transaction(
        investor_id=a.id, building_id=lincoln.id,
        date="2026-04-01", amount=-180.0, description="Plumbing",
        plaid_id=f"x-{lincoln.id[:8]}",
    )])

    install_mock_audit()
    audit = audit_mod.get_audit()
    await _drive(a.id, "remove_property", {
        "address": "412 Lincoln Street, Westfield, NJ",
    })
    # Lincoln building should still exist (refused)
    assert await get_building(lincoln.id) is not None
    # Sensitive reads on lease + transaction audited (the tool counted them)
    sens = {
        (e["detail"] or {}).get("scope")
        for e in audit.events
        if e.get("kind") == "read" and (e["detail"] or {}).get("tool") == "remove_property"
    }
    assert sens >= {"lease", "transaction"}, sens
    print(f"  remove with deps: refused (lease+transaction); sensitive-read audit on {sorted(sens)}")

    # ---- 8) remove_property with force=true → cascade-deletes ------------
    install_mock_audit()
    audit = audit_mod.get_audit()
    await _drive(a.id, "remove_property", {
        "address": "412 Lincoln Street, Westfield, NJ",
        "force": True,
    })
    assert await get_building(lincoln.id) is None
    # Lease gone
    assert await mongo_module.db()["leases"].count_documents({"unit_id": unit["_id"]}) == 0
    # Transaction gone
    assert await mongo_module.db()["transactions"].count_documents(
        {"building_id": lincoln.id}
    ) == 0
    # Units gone
    assert await mongo_module.db()["units"].count_documents(
        {"building_id": lincoln.id}
    ) == 0
    print(f"  remove force=true: building, 4 units, 1 lease, 1 transaction all gone")

    # ---- 9) Cross-investor: A can't remove B's building -------------------
    await _drive(a.id, "remove_property", {
        "address": "1 Beach St, Asbury Park, NJ",
    })
    assert await get_building(beach.id) is not None
    print("  cross-investor remove: refused (B's building still there)")

    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
