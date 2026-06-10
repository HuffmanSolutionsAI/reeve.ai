"""Ana v2 end-to-end: routing on deal.profile, the bundle read, the
engine invocation, the value_add_analysis terminal submission.

Mocks the LLM with a scripted tool-call sequence and drives Ana through
the runtime; mongomock holds the staged rent_roll + operating_statement
and the artifact write."""
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
from reeve.models.underwriting import (
    AbatementAllowance,
    AncillaryItem,
    AncillaryKind,
    BridgeFinancing,
    BudgetTier,
    CapRates,
    CompCondition,
    ConditionInventory,
    ConditionTier,
    DealAssumptions,
    FinancingScenario,
    InsuranceQuoteSource,
    InsuranceRecord,
    LeaseRow,
    MarketContext,
    OccupancyGate,
    OpExCategory,
    OperatingLine,
    OperatingPeriod,
    OperatingStatement,
    PermFinancing,
    PropertyProfile,
    Provenance,
    RentComp,
    RenovationBudget,
    RentRoll,
    RequiredMargin,
    RequiredMarginType,
    Site,
    Sourced,
    Structure,
    StructureType,
    TargetRent,
    TaxReassessmentMethod,
    TaxRecord,
    UtilityRecord,
)
from reeve.repos.deals import get_deal, upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.repos.operating_statements import insert_operating_statement
from reeve.repos.rent_rolls import insert_rent_roll
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
    """Scripted LLM with a callback for sourcing the submit payload from
    the prior turn's tool result."""

    def __init__(self, scripted: list[Any], capture: dict) -> None:
        self._scripted = list(scripted)
        self.messages = self
        self._capture = capture

    async def create(self, **kw: Any) -> _Resp:
        item = self._scripted.pop(0)
        if callable(item):
            return item(self._capture)
        return item


async def main() -> None:
    print("smoke_ana_value_add:")
    install_mock_db()
    audit = _InMemoryAudit()
    audit_mod.set_default(audit)

    investor = Investor(name="J", buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20, target_coc=0.08))
    await upsert_investor(investor)

    # ---- build the v2 deal (same shape as the engine smoke, condensed) -
    profile = PropertyProfile(
        structures=[
            Structure(label="main", structure_type=StructureType.APARTMENTS,
                      year_built=1960, units_count=24),
            Structure(label="clubhouse", structure_type=StructureType.CLUBHOUSE,
                      year_built=1940),
        ],
        condition_inventory=ConditionInventory(renovated=8, rent_ready=10, down=6),
        physical_occupancy=Sourced(value=0.625, prov=Provenance.VERIFIED),
        site=Site(parking_spaces=18, parking_scarce=True, storage_dead_space=True),
        submarket="Westfield NJ",
    )
    budget = RenovationBudget(
        tiers=[
            BudgetTier(condition_tier=ConditionTier.DOWN,
                       scope_description="full reno",
                       cost_per_unit=Sourced(value=32000, prov=Provenance.ASSUMED),
                       units_count=6),
            BudgetTier(condition_tier=ConditionTier.RENT_READY,
                       scope_description="light reno",
                       cost_per_unit=Sourced(value=8000, prov=Provenance.ASSUMED),
                       units_count=10),
        ],
        make_ready_per_unit=1500.0,
        abatement=AbatementAllowance(amount=20000, basis="5% of reno", tested=False),
        contingency_pct=0.20,
    )
    market = MarketContext(
        rent_comps=[
            RentComp(condition=CompCondition.RENOVATED, beds=1, baths=1.0, rent=1550),
            RentComp(condition=CompCondition.CLASSIC, beds=1, baths=1.0, rent=1100),
        ],
        cap_rates=CapRates(class_c=0.075),
        asset_class="c",
        vacancy_norm=Sourced(value=0.05, prov=Provenance.VERIFIED),
    )
    financing = FinancingScenario(
        label="Bridge → SBL",
        bridge=BridgeFinancing(ltc=0.75, rate=0.105, term_months=24, expected_hold_months=18),
        perm=PermFinancing(rate=0.0675, amort_years=30, min_dscr=1.25, max_ltv=0.75,
                           occupancy_gate=OccupancyGate(occupancy=0.90, days=90)),
    )
    assumptions = DealAssumptions(
        target_rents=[
            TargetRent(condition_tier=ConditionTier.RENOVATED, monthly_rent=1500),
            TargetRent(condition_tier=ConditionTier.RENT_READY, monthly_rent=1500),
            TargetRent(condition_tier=ConditionTier.DOWN, monthly_rent=1500),
        ],
        exit_cap=0.065,
        required_margin=RequiredMargin(margin_type=RequiredMarginType.PCT_OF_COST, value=0.15),
        stabilized_vacancy=0.05, credit_loss=0.02, rent_growth=0.03, lease_up_months=12,
        ancillary=[
            AncillaryItem(item=AncillaryKind.RUBS, monthly=1800),
            AncillaryItem(item=AncillaryKind.PARKING, monthly=900),
        ],
    )

    deal = Deal(
        investor_id=investor.id, address="100 Test St",
        units=24, ask=2_400_000,
        source=DealSource.MANUAL, status=DealStatus.ANALYZED,
        profile=DealProfile.VALUE_ADD,
        property_profile=profile, renovation_budget=budget,
        market_context=market, financing_scenarios=[financing], assumptions=assumptions,
    )
    await upsert_deal(deal)

    # ---- rent roll + operating statement (staged + confirmed) ---------
    leases = []
    for i in range(6):
        leases.append(LeaseRow(
            unit_label=f"R{i+1}", condition_tier=ConditionTier.RENOVATED, occupied=True,
            in_place_rent=Sourced(value=1500, prov=Provenance.VERIFIED),
            achieved_rent=Sourced(value=1500, prov=Provenance.VERIFIED),
        ))
    for i in range(2):
        leases.append(LeaseRow(unit_label=f"RV{i+1}", condition_tier=ConditionTier.RENOVATED, occupied=False))
    for i in range(7):
        leases.append(LeaseRow(
            unit_label=f"RR{i+1}", condition_tier=ConditionTier.RENT_READY, occupied=True,
            in_place_rent=Sourced(value=1100, prov=Provenance.VERIFIED),
        ))
    for i in range(3):
        leases.append(LeaseRow(unit_label=f"RRV{i+1}", condition_tier=ConditionTier.RENT_READY, occupied=False))
    for i in range(2):
        leases.append(LeaseRow(
            unit_label=f"D{i+1}", condition_tier=ConditionTier.DOWN, occupied=True,
            in_place_rent=Sourced(value=900, prov=Provenance.VERIFIED),
        ))
    for i in range(4):
        leases.append(LeaseRow(unit_label=f"DV{i+1}", condition_tier=ConditionTier.DOWN, occupied=False))

    rr = RentRoll(
        deal_id=deal.id, investor_id=investor.id, as_of="2026-06-01",
        leases=leases, human_confirmed=True, confirmed_by=investor.id,
        confirmed_at="2026-06-02",
    )
    await insert_rent_roll(rr)
    opex = OperatingStatement(
        deal_id=deal.id, investor_id=investor.id,
        period=OperatingPeriod(start="2025-05-01", end="2026-04-30"),
        lines=[
            OperatingLine(category=OpExCategory.TAXES, annual=Sourced(value=18000, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.INSURANCE, annual=Sourced(value=6500, prov=Provenance.BROKER_CLAIMED)),
            OperatingLine(category=OpExCategory.UTILITIES_WATER, annual=Sourced(value=14400, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.MGMT_FEE, annual=Sourced(value=18500, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.REPAIRS_MAINTENANCE, annual=Sourced(value=22000, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.PAYROLL, annual=Sourced(value=24000, prov=Provenance.VERIFIED)),
        ],
        tax=TaxRecord(
            current_assessed=Sourced(value=1_100_000, prov=Provenance.VERIFIED),
            current_annual_bill=Sourced(value=18000, prov=Provenance.VERIFIED),
            reassessment_method=TaxReassessmentMethod.MILLAGE_AT_PRICE,
            millage_rate=0.022,
        ),
        insurance=InsuranceRecord(current_annual=Sourced(value=6500, prov=Provenance.BROKER_CLAIMED)),
        utilities=UtilityRecord(master_metered=["water"], rubs_candidate=True),
        reserves_per_door=300.0,
        human_confirmed=True, confirmed_by=investor.id, confirmed_at="2026-06-02",
    )
    await insert_operating_statement(opex)
    deal.active_rent_roll_id = rr.id
    deal.active_operating_statement_id = opex.id
    await upsert_deal(deal)
    print(f"  seed: 24-unit value_add deal at $2.4M ask, profile={deal.profile}")

    # ---- script the LLM through Ana's v2 flow -------------------------
    captured: dict = {}

    def submit_after_run(capture):
        # Build a submit turn using the run_value_add_analysis result.
        payload = capture["run_result"]
        return _Resp([
            _Block("text", text="Conditional pursue ≤ ceiling; blocking flags must clear."),
            _Block("tool_use", id="t3", name="submit_value_add_analysis",
                   input={"artifact": payload, "deal_id": deal.id}),
        ])

    scripted = [
        # Turn 1: inputs check
        _Resp([_Block("tool_use", id="t1", name="get_deal_underwriting_inputs",
                      input={"deal_id": deal.id})]),
        # Turn 2: run engine
        _Resp([_Block("tool_use", id="t2", name="run_value_add_analysis",
                      input={"deal_id": deal.id, "bid_price": 2_400_000})]),
        # Turn 3: submit using captured run_result
        submit_after_run,
    ]
    llm_mod.set_async_client(_FakeAnthropic(scripted, captured))

    # Patch the runner so we can capture the tool-result payload between turns.
    # We hijack the value of `run_value_add_analysis` to store it.
    from reeve.runtime import REGISTRY
    original = REGISTRY["run_value_add_analysis"].handler

    async def capturing_run(**kw):
        result = await original(**kw)
        if result.get("ok"):
            captured["run_result"] = result["result"]
        return result

    REGISTRY["run_value_add_analysis"].handler = capturing_run

    ana = load_agent("ana")
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(ana, "Underwrite 100 Test St; profile value_add.", ctx)

    # Restore.
    REGISTRY["run_value_add_analysis"].handler = original

    # ---- assertions ----------------------------------------------------
    assert result.artifact is not None, "Ana did not produce an artifact"
    assert result.artifact["type"] == "value_add_analysis"
    assert result.artifact["verdict"]["decision"] == "conditional"
    assert result.artifact["confidence"] == "low"
    assert "artifact_id" in result.artifact
    print(
        f"  ana: tools={result.tools_called}, "
        f"artifact_id={result.artifact['artifact_id'][:8]}…, "
        f"decision={result.artifact['verdict']['decision']}"
    )

    # Deal advanced and points at the new artifact.
    deal_after = await get_deal(deal.id)
    assert deal_after.latest_analysis_id == result.artifact["artifact_id"]
    print(f"  deal.latest_analysis_id updated → {deal_after.latest_analysis_id[:8]}…")

    # Persisted artifact body matches the contract type.
    art = await mongo_module.db()["artifacts"].find_one({"_id": result.artifact["artifact_id"]})
    assert art["type"] == "value_add_analysis"
    assert art["produced_by"] == "ana"
    print(f"  persisted artifact: type={art['type']}, version={art['version']}")

    # Sensitive reads on lease + transaction audited.
    sens_scopes = {
        (e["detail"] or {}).get("scope") for e in audit.events
        if e.get("kind") == "read" and (e["detail"] or {}).get("scope") in {"lease", "transaction"}
    }
    assert sens_scopes >= {"lease", "transaction"}, sens_scopes
    print(f"  audit: sensitive reads fired on {sorted(sens_scopes)}")

    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
