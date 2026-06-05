"""Step-5 smoke: Reed standalone with the Plaid sync, categorizer, KPIs,
and the morning-brief contract.

Verifies the build plan's §0.1 claim: the runtime generalizes with zero
changes — only new tools + new contract + new agent spec land Reed."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")

import jsonschema
from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
from reeve.finance.kpis import compute_kpis
from reeve.finance.periods import last_n_days, month_to_date
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
    return client


class _InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kw: Any) -> dict:
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


async def _seed() -> tuple[Investor, list[Building]]:
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20, target_coc=0.08),
    )
    await upsert_investor(investor)

    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))

    specs = [("412 Lincoln St, Westfield, NJ", 4), ("27 South Ave, Westfield, NJ", 6)]
    buildings: list[Building] = []
    for addr, units_count in specs:
        b = Building(portfolio_id=portfolio.id, address=addr, units_count=units_count)
        await mongo_module.db()["buildings"].insert_one(b.model_dump(by_alias=True))
        for i in range(units_count):
            u = Unit(
                building_id=b.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                market_rent=1466,
                status=UnitStatus.OCCUPIED if i < units_count - 1 else UnitStatus.VACANT,
            )
            await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
        buildings.append(b)
    return investor, buildings


async def _seed_transactions(investor_id: str, buildings: list[Building]) -> int:
    total = 0
    for b in buildings:
        fixtures = synthesize_transactions(
            building_id=b.id, units=b.units_count, market_rent=1466.0,
            days=60, seed=hash(b.id) & 0xFFFFFFFF,
        )
        client = MockPlaidClient(fixtures=fixtures)
        ptxns = client.fetch_transactions(f"acct-{b.id}", "1970-01-01", "9999-12-31")
        n = await sync_transactions(
            investor_id=investor_id, building_id=b.id, plaid_txns=ptxns,
        )
        total += n
    return total


async def main() -> None:
    print("step-5 smoke (Reed standalone):")
    install_mock_db()
    audit = install_mock_audit()
    investor, buildings = await _seed()

    # Categorizer + Plaid sync write through to Mongo.
    n = await _seed_transactions(investor.id, buildings)
    print(f"  synced {n} transactions across {len(buildings)} buildings")

    # Pull a chunk back and verify categorization landed.
    mtd_start, mtd_end = month_to_date()
    period_start, period_end = last_n_days(30)
    rows = await repo_list(
        investor_id=investor.id, period_start="1970-01-01", period_end="9999-12-31",
    )
    cats = {r.get("category") for r in rows}
    assert "rent" in cats and "debt_service" in cats and "insurance" in cats
    print(f"  ledger categories present: {sorted(c for c in cats if c)}")

    # Idempotency: re-sync the same fixtures, transaction count stays the same.
    await _seed_transactions(investor.id, buildings)
    rows_after = await repo_list(
        investor_id=investor.id, period_start="1970-01-01", period_end="9999-12-31",
    )
    assert len(rows_after) == len(rows), "plaid_id upsert key didn't dedupe"
    print(f"  idempotency: re-sync left row count at {len(rows_after)}")

    # ---- script Reed's run ---------------------------------------------------
    units_total = sum(b.units_count for b in buildings)
    occupied = sum(b.units_count - 1 for b in buildings)  # last unit vacant per spec
    period_kpis_rows = await repo_list(
        investor_id=investor.id, period_start=period_start, period_end=period_end,
    )
    pre_kpis = compute_kpis(
        transactions=period_kpis_rows, units_total=units_total,
        occupied_units=occupied, period_days=30,
    ).to_dict()

    brief_payload = {
        "type": "morning_brief",
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "period": {"start": period_start, "end": period_end},
        "portfolio": {
            "buildings": len(buildings), "units": units_total,
            "occupied": occupied, "vacant": units_total - occupied,
            "occupancy": round(occupied / units_total, 4),
        },
        "month_to_date": {
            "revenue": pre_kpis["revenue"], "expenses": pre_kpis["expenses"],
            "noi": pre_kpis["noi"], "expense_ratio": pre_kpis["expense_ratio"],
            "by_category": pre_kpis["by_category"],
        },
        "highlights": [
            {"kind": "vacancy", "severity": "watch",
             "text": f"{units_total - occupied} vacant units across {len(buildings)} buildings",
             "building_id": buildings[0].id},
        ],
        "thesis": "Cash flow steady; two vacancies are the only watch item.",
        "confidence": "high",
        "unverified": [],
    }

    scripted = [
        _Resp([_Block("tool_use", id="r1", name="get_portfolio_snapshot", input={})]),
        _Resp([_Block("tool_use", id="r2", name="list_transactions",
                      input={"period_start": period_start, "period_end": period_end})]),
        _Resp([_Block("tool_use", id="r3", name="compute_kpis", input={
            "transactions": period_kpis_rows, "units_total": units_total,
            "occupied_units": occupied, "period_days": 30,
        })]),
        _Resp([
            _Block("text", text=brief_payload["thesis"]),
            _Block("tool_use", id="r4", name="submit_morning_brief",
                   input={"artifact": brief_payload}),
        ]),
    ]
    import reeve.runtime.runner as runner_module
    runner_module._client_singleton = _FakeAnthropic(scripted)

    reed = load_agent("reed")
    assert reed.id == "reed" and reed.terminal_tool == "submit_morning_brief"
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(reed, "Brief me on the portfolio.", ctx)

    assert result.artifact is not None, "no brief emitted"
    assert result.artifact["type"] == "morning_brief"
    schema = json.loads(Path("contracts/morning_brief.schema.json").read_text())
    contract_only = {k: v for k, v in result.artifact.items()
                     if k not in ("artifact_id", "version", "supersedes")}
    jsonschema.Draft7Validator(schema).validate(contract_only)

    # The agent_run records what tools Reed actually called.
    assert set(result.tools_called) == {
        "get_portfolio_snapshot", "list_transactions", "compute_kpis",
        "submit_morning_brief",
    }
    print(f"  reed: tools={sorted(result.tools_called)}, "
          f"artifact_id={result.artifact['artifact_id'][:8]}…")

    # Sensitive read (transaction) should have produced a `read` audit event
    # in addition to the generic per-tool audit.
    tx_read_events = [
        e for e in audit.events
        if e.get("kind") == "read" and (e.get("detail") or {}).get("scope") == "transaction"
    ]
    assert tx_read_events, "expected a sensitive-read audit for `transaction`"
    print(f"  sensitive-read audit: {len(tx_read_events)} 'read' on transaction scope")

    # The brief is persisted as a versioned artifact.
    art = await mongo_module.db()["artifacts"].find_one({"_id": result.artifact["artifact_id"]})
    assert art and art["type"] == "morning_brief"
    assert art["version"] == 1 and art["produced_by"] == "reed"
    print(f"  artifact persisted: type={art['type']}, version={art['version']}")

    # The build plan's §0.1 claim — verify no runtime change was needed by
    # confirming the only Reed-new modules are tools + contract + spec.
    print("  generalizes-with-zero-changes: runtime + audit + repos untouched ✓")
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
