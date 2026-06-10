"""Ingestion smoke: chat-entry tools → staged documents → machine
validation → human confirmation gate → engine unblocked.

Covers the §8 lifecycle end to end:
  1. Ana (scripted LLM) enters the deal bundle via update_deal_underwriting,
     then ingests a rent roll and a T-12 via the ingest tools.
  2. Both documents land STAGED: human_confirmed=False, and the deal's
     active_*_id pointers are NOT set (the tool cannot activate).
  3. Machine validation runs at ingest: a deliberate claimed-unit-count
     mismatch is recorded as a failed check (ingest still succeeds —
     failed checks block confidence, not entry).
  4. GET /api/documents/pending lists both documents with their checks.
  5. POST /api/*/confirm (investor-authenticated) flips human_confirmed,
     sets the deal's active pointers, and audits APPROVED events.
  6. Cross-investor confirm → 404.
  7. After confirmation, get_deal_underwriting_inputs reports missing=[]
     and run_value_add_analysis produces a full result — the loop closes.
  8. Structural: the ingest tools' input schemas contain no
     human_confirmed parameter (the gate is unreachable from the agent)."""
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
from reeve.models import BuyBox, Deal, DealSource, DealStatus, Investor
from reeve.models.deal import DealProfile
from reeve.repos.deals import get_deal, upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.runtime import REGISTRY, RunContext, load_agent, run_agent


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


# The bundle Ana would compose from the investor's chat description.
def _bundle_inputs(deal_id: str) -> dict:
    return {
        "deal_id": deal_id,
        "profile": "value_add",
        "property_profile": {
            "structures": [
                {"label": "main", "structure_type": "apartments", "year_built": 1960, "units_count": 24},
                {"label": "clubhouse", "structure_type": "clubhouse", "year_built": 1940, "units_count": 0},
            ],
            "condition_inventory": {"renovated": 8, "rent_ready": 10, "down": 6},
            "physical_occupancy": {"value": 0.625, "prov": "verified", "citation": "investor walk"},
            "site": {"parking_spaces": 18, "parking_scarce": True, "storage_dead_space": True},
            "submarket": "Westfield NJ",
        },
        "renovation_budget": {
            "tiers": [
                {"condition_tier": "down", "scope_description": "full reno",
                 "cost_per_unit": {"value": 32000, "prov": "assumed"}, "units_count": 6},
                {"condition_tier": "rent_ready", "scope_description": "light reno",
                 "cost_per_unit": {"value": 8000, "prov": "assumed"}, "units_count": 10},
            ],
            "make_ready_per_unit": 1500,
            "abatement": {"amount": 20000, "basis": "5% of reno", "tested": False},
            "contingency_pct": 0.20,
        },
        "market_context": {
            "rent_comps": [
                {"condition": "renovated", "beds": 1, "baths": 1.0, "rent": 1550},
                {"condition": "classic", "beds": 1, "baths": 1.0, "rent": 1100},
            ],
            "cap_rates": {"class_c": 0.075},
            "asset_class": "c",
            "vacancy_norm": {"value": 0.05, "prov": "verified"},
        },
        "financing_scenarios": [{
            "label": "Bridge → SBL",
            "bridge": {"ltc": 0.75, "rate": 0.105, "term_months": 24, "expected_hold_months": 18},
            "perm": {"rate": 0.0675, "amort_years": 30, "min_dscr": 1.25, "max_ltv": 0.75,
                     "occupancy_gate": {"occupancy": 0.90, "days": 90}},
        }],
        "assumptions": {
            "target_rents": [
                {"condition_tier": "renovated", "monthly_rent": 1500},
                {"condition_tier": "rent_ready", "monthly_rent": 1500},
                {"condition_tier": "down", "monthly_rent": 1500},
            ],
            "exit_cap": 0.065,
            "required_margin": {"margin_type": "pct_of_cost", "value": 0.15},
            "stabilized_vacancy": 0.05, "credit_loss": 0.02, "lease_up_months": 12,
            "ancillary": [{"item": "rubs", "monthly": 1800, "basis": "master-metered water"}],
        },
    }


def _rent_roll_inputs(deal_id: str) -> dict:
    leases = []
    for i in range(6):
        leases.append({"unit_label": f"R{i+1}", "condition_tier": "renovated", "occupied": True,
                       "in_place_rent": 1500, "achieved_rent": 1500})
    for i in range(2):
        leases.append({"unit_label": f"RV{i+1}", "condition_tier": "renovated", "occupied": False})
    for i in range(7):
        leases.append({"unit_label": f"RR{i+1}", "condition_tier": "rent_ready", "occupied": True,
                       "in_place_rent": 1100})
    for i in range(3):
        leases.append({"unit_label": f"RRV{i+1}", "condition_tier": "rent_ready", "occupied": False})
    for i in range(2):
        leases.append({"unit_label": f"D{i+1}", "condition_tier": "down", "occupied": True,
                       "in_place_rent": 900})
    for i in range(4):
        leases.append({"unit_label": f"DV{i+1}", "condition_tier": "down", "occupied": False})
    return {
        "deal_id": deal_id,
        "as_of": "2026-06-01",
        "leases": leases,
        "provenance": "broker_claimed",
        "source_description": "pasted from OM PDF p.12",
        # DELIBERATE mismatch: document claims 26 units; we extracted 24.
        # Machine validation must record the failure; ingest still succeeds.
        "claimed_unit_count": 26,
        "stated_monthly_total": 18500.0,   # rows sum to 18500 → passes
    }


def _opex_inputs(deal_id: str) -> dict:
    return {
        "deal_id": deal_id,
        "period_start": "2025-05-01",
        "period_end": "2026-04-30",
        "lines": [
            {"category": "taxes", "annual": 18000},
            {"category": "insurance", "annual": 6500},
            {"category": "utilities_water", "annual": 14400},
            {"category": "mgmt_fee", "annual": 18500},
            {"category": "repairs_maintenance", "annual": 22000},
            {"category": "payroll", "annual": 24000},
        ],
        "provenance": "broker_claimed",
        "tax": {"current_assessed": 1100000, "current_annual_bill": 18000, "millage_rate": 0.022},
        "insurance": {"current_annual": 6500},
        "utilities": {"master_metered": ["water"], "rubs_candidate": True},
        "source_description": "T-12 xlsx from broker",
        "stated_annual_total": 103400.0,
    }


async def main() -> None:
    print("smoke_ingestion:")
    install_mock_db()
    audit = _InMemoryAudit()
    audit_mod.set_default(audit)

    # ---- 8) structural: no human_confirmed parameter on the ingest tools
    for tool_name in ("ingest_rent_roll", "ingest_operating_statement"):
        schema_props = REGISTRY[tool_name].input_schema["properties"]
        assert "human_confirmed" not in schema_props, tool_name
        assert "active" not in schema_props, tool_name
    print("  structural: ingest tools cannot set human_confirmed (no such parameter)")

    investor = Investor(name="J", email="j@test.example",
                        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20))
    await upsert_investor(investor)
    other = Investor(name="Mallory", email="m@test.example")
    await upsert_investor(other)

    deal = Deal(investor_id=investor.id, address="100 Test St", units=24,
                ask=2_400_000, source=DealSource.MANUAL, status=DealStatus.SOURCED)
    await upsert_deal(deal)

    # ---- 1) Ana enters the bundle + ingests both documents (one run) ----
    scripted = [
        _Resp([_Block("tool_use", id="t1", name="update_deal_underwriting",
                      input=_bundle_inputs(deal.id))]),
        _Resp([_Block("tool_use", id="t2", name="ingest_rent_roll",
                      input=_rent_roll_inputs(deal.id))]),
        _Resp([_Block("tool_use", id="t3", name="ingest_operating_statement",
                      input=_opex_inputs(deal.id))]),
        _Resp([_Block("text", text="Bundle entered; both documents staged. "
                                   "Review and confirm under Approvals, then I can underwrite.")]),
    ]
    llm_mod.set_async_client(_FakeAnthropic(scripted))
    ana = load_agent("ana")
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(ana, "Set up 100 Test St as value-add; here's the data…", ctx)
    assert set(result.tools_called) == {
        "update_deal_underwriting", "ingest_rent_roll", "ingest_operating_statement",
    }, result.tools_called
    print(f"  ana entered bundle + ingested both documents: {sorted(result.tools_called)}")

    # ---- 2) deal bundle written; documents STAGED, pointers NOT set ----
    deal_after = await get_deal(deal.id)
    assert deal_after.profile == "value_add"
    assert deal_after.property_profile is not None
    assert deal_after.assumptions is not None
    assert deal_after.active_rent_roll_id is None, "tool must NOT activate the roll"
    assert deal_after.active_operating_statement_id is None, "tool must NOT activate the T-12"

    rr_doc = await mongo_module.db()["rent_rolls"].find_one({"deal_id": deal.id})
    op_doc = await mongo_module.db()["operating_statements"].find_one({"deal_id": deal.id})
    assert rr_doc is not None and rr_doc["human_confirmed"] is False
    assert op_doc is not None and op_doc["human_confirmed"] is False
    print("  staged: human_confirmed=False on both; deal.active_*_id still None")

    # ---- 3) machine validation recorded the deliberate mismatch --------
    rr_checks = {c["name"]: c for c in rr_doc["validation"]["checks"]}
    assert rr_checks["row_count_matches_claimed_units"]["passed"] is False
    assert rr_checks["rent_sum_matches_stated_total"]["passed"] is True
    assert rr_checks["occupied_rows_have_rent"]["passed"] is True
    op_checks = {c["name"]: c for c in op_doc["validation"]["checks"]}
    assert op_checks["period_is_full_year"]["passed"] is True
    assert op_checks["line_sum_matches_stated_total"]["passed"] is True
    print(f"  validation: row-count mismatch RECORDED "
          f"({rr_checks['row_count_matches_claimed_units']['detail']})")

    # ---- 4-6) review + confirm via the API ------------------------------
    from fastapi.testclient import TestClient
    from reeve.api import build_app
    from reeve.api.auth import issue_token

    app = build_app()
    with TestClient(app) as client:
        h_owner = {"Authorization": f"Bearer {issue_token(investor.id)['access_token']}"}
        h_other = {"Authorization": f"Bearer {issue_token(other.id)['access_token']}"}

        r = client.get("/api/documents/pending", headers=h_owner)
        assert r.status_code == 200, r.text
        pending = r.json()
        assert len(pending["rent_rolls"]) == 1
        assert len(pending["operating_statements"]) == 1
        assert pending["rent_rolls"][0]["deal_address"] == "100 Test St"
        failed_names = [
            c["name"] for c in pending["rent_rolls"][0]["validation"]["checks"]
            if not c["passed"]
        ]
        assert "row_count_matches_claimed_units" in failed_names
        print(f"  /documents/pending: 1 roll + 1 T-12; failed check surfaced to the review UI")

        # Cross-investor confirm → 404 (no existence leak)
        r = client.post(f"/api/rent-rolls/{rr_doc['_id']}/confirm", headers=h_other)
        assert r.status_code == 404, r.status_code
        print("  cross-investor confirm → 404")

        # Owner confirms both
        r = client.post(f"/api/rent-rolls/{rr_doc['_id']}/confirm", headers=h_owner)
        assert r.status_code == 200, r.text
        assert r.json()["active"] is True
        r = client.post(f"/api/operating-statements/{op_doc['_id']}/confirm", headers=h_owner)
        assert r.status_code == 200, r.text

        # Double-confirm → 400
        r = client.post(f"/api/rent-rolls/{rr_doc['_id']}/confirm", headers=h_owner)
        assert r.status_code == 400
        print("  owner confirmed both; double-confirm → 400")

    deal_final = await get_deal(deal.id)
    assert deal_final.active_rent_roll_id == rr_doc["_id"]
    assert deal_final.active_operating_statement_id == op_doc["_id"]
    approved = [e for e in audit.events if e.get("kind") == "approved"]
    assert {e["entity_type"] for e in approved} == {"rent_roll", "operating_statement"}
    print("  pointers flipped by the CONFIRM endpoint; audit: 2 'approved' events")

    # ---- 7) the loop closes: inputs complete, engine runs ----------------
    inputs_handler = REGISTRY["get_deal_underwriting_inputs"].handler
    bundle = await inputs_handler(deal_id=deal.id, _ctx=ctx)
    assert bundle["missing"] == [], bundle["missing"]

    run_handler = REGISTRY["run_value_add_analysis"].handler
    engine = await run_handler(deal_id=deal.id, _ctx=ctx, bid_price=2_400_000)
    assert engine["ok"] is True
    res = engine["result"]
    flag_codes = {f["code"] for f in res["flags"]}
    # unconfirmed_extraction must NOT be among the flags anymore.
    assert "unconfirmed_extraction" not in flag_codes, flag_codes
    print(f"  post-confirm: missing=[], engine runs; "
          f"unconfirmed_extraction cleared (open flags: {sorted(flag_codes)})")

    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
