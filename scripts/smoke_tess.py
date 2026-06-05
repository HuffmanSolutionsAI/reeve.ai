"""Step-12 smoke: Tess — tax estimate + gated filing.

Drives Tess against a synthesized ledger:
  - Reads transactions for the tax year, computes annual gross income +
    operating expenses (excluding debt_service principal portion).
  - Calls estimate_liability with the portfolio's basis.
  - Submits a tax_memo artifact (terminal ACT_INTERNAL).
  - Optionally calls submit_tax_filing — intercepted by the runner,
    queued as a proposal; API approve fires the gated handler which
    writes a tax_filing_record artifact for the audit trail."""
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
from reeve.finance.plaid import MockPlaidClient, sync_transactions
from reeve.finance.seed import synthesize_transactions
from reeve.models import (
    Building,
    BuyBox,
    Financing,
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
    investor = Investor(name="James M.", entity_name="Oakwood Holdings",
                        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20))
    await upsert_investor(investor)
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    building = Building(
        portfolio_id=portfolio.id, address="412 Lincoln St",
        units_count=8, basis=1_200_000,  # depreciable basis
        financing=Financing(rate=0.0675, term=25, ltv=0.70),
    )
    await mongo_module.db()["buildings"].insert_one(building.model_dump(by_alias=True))
    for i in range(8):
        u = Unit(building_id=building.id, label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                 market_rent=1466, status=UnitStatus.OCCUPIED)
        await mongo_module.db()["units"].insert_one(u.model_dump(by_alias=True))
    # 12 months of synthetic transactions.
    fixtures = synthesize_transactions(
        building_id=building.id, units=building.units_count,
        market_rent=1466.0, days=365, seed=9999,
    )
    client = MockPlaidClient(fixtures=fixtures)
    ptxns = client.fetch_transactions(f"acct-{building.id}", "1970-01-01", "9999-12-31")
    await sync_transactions(
        investor_id=investor.id, building_id=building.id, plaid_txns=ptxns,
    )
    return investor, building


async def main() -> None:
    print("step-12 smoke (Tess — tax):")
    install_mock_db()
    audit = install_mock_audit()
    investor, building = await _seed()

    # Build the inputs Tess would derive from list_transactions.
    txns = await repo_list(
        investor_id=investor.id,
        period_start="2026-01-01", period_end="2026-12-31",
        limit=5000,
    )
    gross = sum(t["amount"] for t in txns if t["amount"] > 0)
    expenses = -sum(t["amount"] for t in txns if t["amount"] < 0 and t.get("category") != "debt_service")
    print(f"  ledger: {len(txns)} txns, gross=${gross:,.0f}, opex=${expenses:,.0f}")

    # Pre-compute the estimate (same path Tess takes via the tool).
    from reeve.runtime.tools.tax import estimate_liability
    est = estimate_liability(
        gross_rental_income=gross,
        operating_expenses=expenses,
        building_basis=float(building.basis),
        federal_rate=0.24,
        state_rate=0.06,
    )

    memo_payload = {
        "type": "tax_memo",
        "as_of": "2026-12-31",
        "tax_year": 2026,
        "period": {"start": "2026-01-01", "end": "2026-12-31"},
        "estimate": est,
        "by_building": [{
            "building_id": building.id, "address": building.address,
            "gross_rental_income": gross, "operating_expenses": expenses,
            "depreciation": est["depreciation"],
            "net_rental_income": est["net_rental_income"],
        }],
        "strategy_flags": [
            {"kind": "cost_segregation", "severity": "watch",
             "text": "Building basis > $500k and within 5 years of acquisition — "
                     "a cost-seg study could accelerate depreciation.",
             "estimated_value": 8000.0},
            {"kind": "filing_deadline", "severity": "info",
             "text": "Federal filing due April 15, 2027."},
        ],
        "filing_due": "2027-04-15",
        "assumptions": [
            "27.5y straight-line depreciation on building basis",
            "Federal marginal rate 24%",
            "State marginal rate 6%",
            "Debt-service principal excluded from operating expenses",
        ],
        "thesis": (
            f"${est['total_liability']:,.0f} estimated total liability "
            f"(federal ${est['federal_liability']:,.0f} + state "
            f"${est['state_liability']:,.0f}); cost-seg study could "
            "meaningfully reduce this."
        ),
        "confidence": "medium",
        "unverified": ["building basis (using book basis, not appraised value)"],
    }

    # ---- script Tess's run --------------------------------------------------
    scripted = [
        _Resp([_Block("tool_use", id="t1", name="list_transactions",
                      input={"period_start": "2026-01-01", "period_end": "2026-12-31"})]),
        _Resp([_Block("tool_use", id="t2", name="estimate_liability", input={
            "gross_rental_income": gross,
            "operating_expenses": expenses,
            "building_basis": float(building.basis),
            "federal_rate": 0.24, "state_rate": 0.06,
        })]),
        _Resp([
            _Block("text", text=memo_payload["thesis"]),
            _Block("tool_use", id="t3", name="submit_tax_memo",
                   input={"artifact": memo_payload}),
        ]),
    ]
    import reeve.llm as llm_mod
    llm_mod.set_async_client(_FakeAnthropic(scripted))

    tess = load_agent("tess")
    assert tess.terminal_tool == "submit_tax_memo"
    assert tess.gated_actions == ["submit_tax_filing"]
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(tess, "Estimate this year's tax.", ctx)

    assert result.artifact is not None and result.artifact["type"] == "tax_memo"
    schema = json.loads(Path("contracts/tax_memo.schema.json").read_text())
    contract_only = {k: v for k, v in result.artifact.items()
                     if k not in ("artifact_id", "version", "supersedes")}
    jsonschema.Draft7Validator(schema).validate(contract_only)
    memo_artifact_id = result.artifact["artifact_id"]
    print(f"  tess memo: total_liability=${result.artifact['estimate']['total_liability']:,.0f}, "
          f"artifact_id={memo_artifact_id[:8]}…")

    # ---- Gated filing path --------------------------------------------------
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="f1", name="submit_tax_filing", input={
            "jurisdiction": "federal",
            "form": "1040 Schedule E",
            "tax_year": 2026,
            "memo_artifact_id": memo_artifact_id,
            "payment_amount": result.artifact["estimate"]["federal_liability"],
            "filer_name": investor.name,
        })]),
        _Resp([_Block("text", text="Federal filing queued.")]),
    ]))
    result2 = await run_agent(tess, "Queue the federal filing.", ctx)
    assert result2.status == "gated" and len(result2.proposal_ids) == 1
    filing_pid = result2.proposal_ids[0]
    print(f"  filing proposal queued: {filing_pid[:8]}…")

    # API approve → execution writes the tax_filing_record artifact.
    from fastapi.testclient import TestClient
    from reeve.api import build_app

    app = build_app()
    from reeve.api.auth import issue_token
    headers = {"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"}
    with TestClient(app) as client:
        client.headers.update(headers)
        r = client.post(f"/api/proposals/{filing_pid}/approve", json={"approver": "james"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executed"] is True
        filing_artifact_id = body["result"]["artifact_id"]
        assert body["result"]["jurisdiction"] == "federal"
        print(f"  approve+execute: filed {body['result']['form']}, "
              f"artifact_id={filing_artifact_id[:8]}…")

    filing_art = await mongo_module.db()["artifacts"].find_one({"_id": filing_artifact_id})
    assert filing_art["payload"]["type"] == "tax_filing_record"
    assert filing_art["payload"]["memo_artifact_id"] == memo_artifact_id
    print(f"  filing artifact references memo {memo_artifact_id[:8]}…")

    # Audit chain. The runner only emits `artifact` for the terminal agent-loop
    # call (the memo); the gated handler's write of the filing-record artifact
    # is covered by the `executed` event on the same proposal.
    kinds = [e.get("kind") for e in audit.events]
    counts = {k: kinds.count(k) for k in set(kinds)}
    assert counts.get("artifact", 0) == 1   # the memo
    assert counts.get("proposed", 0) == 1
    assert counts.get("approved", 0) == 1
    assert counts.get("executed", 0) == 1
    # Both artifacts actually live in Mongo (memo + filing record).
    n_arts = await mongo_module.db()["artifacts"].count_documents({"produced_by": "tess"})
    assert n_arts == 2, n_arts
    print(f"  audit: {len(audit.events)} events, {counts}; artifacts in store: {n_arts}")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
