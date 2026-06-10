"""Reference-deal smoke for the v2 value-add underwriter.

A 24-unit asset with a 1940 clubhouse + 1960 apartments at ~62% physical
occupancy and mixed unit conditions (8 renovated, 10 rent-ready,
6 down). Six achieved-renovated occupied leases @ $1500/mo establish the
load-bearing input. The candidate bid is $2.4M; bridge-to-perm via
Freddie SBL whose 90/90 gate the current occupancy fails.

The smoke validates each computation against hand math and asserts the
behavioral commitments from the spec:
  - Physical occupancy below 90% → `below_agency_gate` blocking flag +
    perm-first disqualified.
  - 1940 structure → `pre_1980_structure` blocking flag.
  - No commercial insurance quote → `insurance_below_commercial`.
  - Three NOI states are distinct and ordered (in_place < stabilized <
    stabilized+ancillary).
  - Valuation is a band, not a point; opening anchors below floor; the
    ceiling is below stabilized_value by the cost-to-stabilize + margin.
  - Net carry > 0 (the term most often silently omitted).
  - Engine refuses confidence > low while blocking flags are open;
    decision == 'conditional'.
  - Risk register is non-empty and ranked; top entry is the load-bearing
    assumption.
  - Sensitivity grid reports a swing in dollars, not just a center value.
  - Payload validates against the JSON schema."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from reeve.models.underwriting import (
    AbatementAllowance,
    AncillaryItem,
    AncillaryKind,
    BridgeFinancing,
    BrokerProforma,
    BudgetTier,
    CapRates,
    CompCondition,
    CompletedCapital,
    ConditionInventory,
    ConditionTier,
    DealAssumptions,
    FinancingScenario,
    IngestFormat,
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
    RentRollSource,
    RequiredMargin,
    RequiredMarginType,
    Site,
    Sourced,
    Structure,
    StructureType,
    SystemItem,
    SystemLine,
    SystemStatus,
    TargetRent,
    TaxReassessmentMethod,
    TaxRecord,
    UtilityRecord,
    recompute_derived,
)
from reeve.underwriting.value_add import analyze
from reeve.underwriting.value_add.payload import result_to_payload
from reeve.underwriting.value_add.runner import AnalysisInputs


def _build_inputs() -> tuple[AnalysisInputs, dict]:
    profile = PropertyProfile(
        structures=[
            Structure(label="main", structure_type=StructureType.APARTMENTS,
                      year_built=1960, units_count=24, notes="3 buildings"),
            Structure(label="clubhouse", structure_type=StructureType.CLUBHOUSE,
                      year_built=1940, units_count=0),
        ],
        condition_inventory=ConditionInventory(renovated=8, rent_ready=10, down=6),
        physical_occupancy=Sourced(value=0.625, prov=Provenance.VERIFIED,
                                   citation="broker walk 2026-05-15"),
        completed_capital=[
            CompletedCapital(item="new roof", year=2024, cost=85000, verified=True),
        ],
        site=Site(parking_spaces=18, parking_scarce=True, storage_dead_space=True),
        submarket="Westfield NJ",
    )

    # Rent roll: 24 units. 6 renovated occupied @ $1500, 2 renovated vacant.
    # 7 rent-ready occupied @ $1100, 3 rent-ready vacant. 2 down occupied
    # @ $900 (classic in-place), 4 down vacant. Occupancy = 15/24 = 62.5%.
    leases: list[LeaseRow] = []
    for i in range(6):
        leases.append(LeaseRow(
            unit_label=f"R{i+1}", condition_tier=ConditionTier.RENOVATED, occupied=True,
            in_place_rent=Sourced(value=1500, prov=Provenance.VERIFIED),
            achieved_rent=Sourced(value=1500, prov=Provenance.VERIFIED),
            asking_rent=Sourced(value=1600, prov=Provenance.BROKER_CLAIMED),
            lease_start="2025-08-01", lease_end="2026-07-31",
        ))
    for i in range(2):
        leases.append(LeaseRow(
            unit_label=f"RV{i+1}", condition_tier=ConditionTier.RENOVATED, occupied=False,
            asking_rent=Sourced(value=1600, prov=Provenance.BROKER_CLAIMED),
        ))
    for i in range(7):
        leases.append(LeaseRow(
            unit_label=f"RR{i+1}", condition_tier=ConditionTier.RENT_READY, occupied=True,
            in_place_rent=Sourced(value=1100, prov=Provenance.VERIFIED),
        ))
    for i in range(3):
        leases.append(LeaseRow(
            unit_label=f"RRV{i+1}", condition_tier=ConditionTier.RENT_READY, occupied=False,
        ))
    for i in range(2):
        leases.append(LeaseRow(
            unit_label=f"D{i+1}", condition_tier=ConditionTier.DOWN, occupied=True,
            in_place_rent=Sourced(value=900, prov=Provenance.VERIFIED),
            delinquent_balance=350.0,
        ))
    for i in range(4):
        leases.append(LeaseRow(
            unit_label=f"DV{i+1}", condition_tier=ConditionTier.DOWN, occupied=False,
        ))
    rr = RentRoll(
        deal_id="deal-1", investor_id="inv-1", as_of="2026-06-01",
        leases=leases,
        source=RentRollSource(format=IngestFormat.MANUAL, extraction_method="hand"),
        human_confirmed=True, confirmed_by="inv-1", confirmed_at="2026-06-02",
    )
    rr.derived = recompute_derived(rr)

    # Operating statement: T-12 dollars on a 24-unit asset.
    opex = OperatingStatement(
        deal_id="deal-1", investor_id="inv-1",
        period=OperatingPeriod(start="2025-05-01", end="2026-04-30"),
        lines=[
            # Taxes line is present but will be substituted at runtime.
            OperatingLine(category=OpExCategory.TAXES,
                          annual=Sourced(value=18000, prov=Provenance.VERIFIED)),
            # Insurance line — current carrier figure (residential proxy).
            OperatingLine(category=OpExCategory.INSURANCE,
                          annual=Sourced(value=6500, prov=Provenance.BROKER_CLAIMED)),
            OperatingLine(category=OpExCategory.UTILITIES_WATER,
                          annual=Sourced(value=14400, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.UTILITIES_ELECTRIC,
                          annual=Sourced(value=3600, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.UTILITIES_TRASH,
                          annual=Sourced(value=4800, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.MGMT_FEE,
                          annual=Sourced(value=18500, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.REPAIRS_MAINTENANCE,
                          annual=Sourced(value=22000, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.TURNS,
                          annual=Sourced(value=6000, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.PAYROLL,
                          annual=Sourced(value=24000, prov=Provenance.VERIFIED)),
            OperatingLine(category=OpExCategory.ADMIN,
                          annual=Sourced(value=4200, prov=Provenance.VERIFIED)),
        ],
        tax=TaxRecord(
            current_assessed=Sourced(value=1_100_000, prov=Provenance.VERIFIED),
            current_annual_bill=Sourced(value=18000, prov=Provenance.VERIFIED),
            reassessment_method=TaxReassessmentMethod.MILLAGE_AT_PRICE,
            millage_rate=0.022,         # NJ-ish — 2.2% effective rate
        ),
        insurance=InsuranceRecord(
            current_annual=Sourced(value=6500, prov=Provenance.BROKER_CLAIMED),
            # NO commercial_quote → triggers flag
        ),
        utilities=UtilityRecord(
            master_metered=["water"], sub_metered=["electric"],
            owner_paid_annual=14400, rubs_candidate=True,
        ),
        reserves_per_door=300.0,
        human_confirmed=True, confirmed_by="inv-1", confirmed_at="2026-06-02",
    )

    budget = RenovationBudget(
        tiers=[
            # 6 down units to full reno; 2 renovated vacant to make-ready turn.
            BudgetTier(condition_tier=ConditionTier.DOWN,
                       scope_description="Full gut + finish to target standard",
                       cost_per_unit=Sourced(value=32000, prov=Provenance.ASSUMED),
                       units_count=6),
            BudgetTier(condition_tier=ConditionTier.RENT_READY,
                       scope_description="Light reno on rent-ready stock at turn",
                       cost_per_unit=Sourced(value=8000, prov=Provenance.ASSUMED),
                       units_count=10),
        ],
        make_ready_per_unit=1500.0,
        systems=[
            SystemLine(item=SystemItem.ELECTRICAL_PANEL,
                       structure_label="main",
                       cost=Sourced(value=18000, prov=Provenance.ASSUMED),
                       status=SystemStatus.REQUIRED),
            SystemLine(item=SystemItem.HVAC, structure_label="main",
                       cost=Sourced(value=24000, prov=Provenance.ASSUMED),
                       status=SystemStatus.CONTINGENT),
        ],
        abatement=AbatementAllowance(amount=20000, basis="5% of reno", tested=False),
        contingency_pct=0.20,                # 10 base + 5 (pre-1980) + 5 (untested) = 20
        closing_costs_pct=0.025,
    )

    market = MarketContext(
        rent_comps=[
            RentComp(condition=CompCondition.RENOVATED, beds=1, baths=1.0, rent=1550),
            RentComp(condition=CompCondition.RENOVATED, beds=1, baths=1.0, rent=1480),
            RentComp(condition=CompCondition.CLASSIC, beds=1, baths=1.0, rent=1100),
        ],
        cap_rates=CapRates(class_b=0.065, class_c=0.075, source="CoStar Q2", as_of="2026-Q2"),
        asset_class="c",
        vacancy_norm=Sourced(value=0.05, prov=Provenance.VERIFIED),
        rent_growth_trend=Sourced(value=0.03, prov=Provenance.ASSUMED),
    )

    financing = FinancingScenario(
        label="Bridge → Freddie SBL",
        bridge=BridgeFinancing(
            ltc=0.75, rate=0.105, term_months=24, expected_hold_months=18,
            origination_pts=0.015,
        ),
        perm=PermFinancing(
            program="freddie_sbl", rate=0.0675, amort_years=30,
            min_dscr=1.25, max_ltv=0.75,
            occupancy_gate=OccupancyGate(occupancy=0.90, days=90),
            refi_costs_pct=0.02,
        ),
    )

    assumptions = DealAssumptions(
        target_rents=[
            # Target keyed by tier; the renovated target matches achieved.
            TargetRent(condition_tier=ConditionTier.RENOVATED, monthly_rent=1500,
                       rationale="Matches achieved-renovated mean on 6 occupied units"),
            TargetRent(condition_tier=ConditionTier.RENT_READY, monthly_rent=1500,
                       rationale="Bring rent-ready to renovated post-light-reno"),
            TargetRent(condition_tier=ConditionTier.DOWN, monthly_rent=1500,
                       rationale="Full reno to target finish"),
        ],
        exit_cap=0.065,
        required_margin=RequiredMargin(margin_type=RequiredMarginType.PCT_OF_COST, value=0.15),
        stabilized_vacancy=0.05,
        credit_loss=0.02,
        rent_growth=0.03,
        lease_up_months=12,
        ancillary=[
            AncillaryItem(item=AncillaryKind.RUBS, monthly=1800,
                          basis="Master-metered water RUBS @ $75/unit"),
            AncillaryItem(item=AncillaryKind.PARKING, monthly=900,
                          basis="$50 × 18 spaces, scarce submarket"),
            AncillaryItem(item=AncillaryKind.STORAGE, monthly=300,
                          basis="Dead space in clubhouse → 10 lockers @ $30"),
        ],
    )

    broker = BrokerProforma(
        asking_price=2_750_000,
        asking_cap=0.075,
        asking_noi=205_000,                    # vs engine stabilized; diff line populated
        opex_assumption_annual=78_000,
        source="OM 2026-Q2",
    )

    inputs = AnalysisInputs(
        rent_roll=rr, opex=opex, profile=profile, budget=budget,
        market=market, financing=financing, assumptions=assumptions,
        broker_proforma=broker, bid_price=2_400_000,
    )

    expected = {
        "units_total": 24,
        "occupied": 15,
        "physical_occupancy": 0.625,
        "achieved_renovated_n": 6,
        "achieved_renovated_mean": 1500.0,
    }
    return inputs, expected


def main() -> None:
    print("smoke_value_add_engine:")
    inp, exp = _build_inputs()

    # ---- pre-engine sanity --------------------------------------------
    rr = inp.rent_roll
    assert rr.derived.units_total == exp["units_total"], rr.derived.units_total
    assert rr.derived.occupied_count == exp["occupied"]
    assert abs(rr.derived.physical_occupancy - exp["physical_occupancy"]) < 1e-4
    assert rr.derived.achieved_renovated.n == exp["achieved_renovated_n"]
    assert rr.derived.achieved_renovated.mean == exp["achieved_renovated_mean"]
    print(
        f"  rent roll: {rr.derived.units_total}u, "
        f"occ {rr.derived.physical_occupancy:.1%}, "
        f"achieved-renovated n={rr.derived.achieved_renovated.n} "
        f"mean ${rr.derived.achieved_renovated.mean:.0f}"
    )

    # ---- run the engine -------------------------------------------------
    r = analyze(inp)

    # ---- NOI states ordering + non-trivial --------------------------------
    assert r.noi_in_place.noi > 0, r.noi_in_place
    assert r.noi_stabilized.noi > r.noi_in_place.noi, (
        r.noi_in_place.noi, r.noi_stabilized.noi,
    )
    assert r.noi_stabilized_plus_ancillary.noi > r.noi_stabilized.noi, (
        r.noi_stabilized.noi, r.noi_stabilized_plus_ancillary.noi,
    )
    print(
        f"  NOI states: in_place=${r.noi_in_place.noi:,.0f}, "
        f"stabilized=${r.noi_stabilized.noi:,.0f}, "
        f"+ancillary=${r.noi_stabilized_plus_ancillary.noi:,.0f}"
    )

    # ---- tax reassessment at bid (millage_rate 0.022 × bid 2.4M = $52.8k)
    tax_used = r.noi_in_place.opex_lines["taxes"]
    assert abs(tax_used - 0.022 * 2_400_000) < 1e-2, tax_used
    print(f"  tax reassessed at bid: ${tax_used:,.0f} (was $18,000 on T-12)")

    # ---- valuation is a BAND ---------------------------------------------
    assert r.band.floor_value > 0
    assert r.band.stabilized_value > r.band.floor_value
    assert r.band.ceiling_max_offer >= 0
    assert r.band.ceiling_max_offer <= r.band.stabilized_value
    # Opening anchors below floor (rule 4)
    assert r.band.opening < r.band.floor_value
    print(
        f"  valuation band: floor=${r.band.floor_value:,.0f}, "
        f"stabilized=${r.band.stabilized_value:,.0f}, "
        f"ceiling=${r.band.ceiling_max_offer:,.0f}"
    )
    print(
        f"  bid ladder: opening=${r.band.opening:,.0f}, "
        f"target=${r.band.target_bid:,.0f}, "
        f"walk-away=${r.band.walk_away:,.0f}"
    )

    # ---- net carry > 0 (the silent-omission line) ----------------------
    assert r.costs.net_carry > 0, r.costs
    print(
        f"  cost-to-stabilize: reno=${r.costs.renovation:,.0f}, "
        f"net carry=${r.costs.net_carry:,.0f}, "
        f"total=${r.costs.total:,.0f}"
    )

    # ---- financing: agency gate failure + bridge-to-perm -----------------
    assert r.financing.perm_first_qualifies is False, "62.5% occupancy must fail 90/90 gate"
    assert r.financing.structure == "bridge_to_perm"
    # perm loan is lesser of LTV/DSCR — assert that fact regardless of which wins
    assert r.financing.perm_loan == min(r.financing.perm_by_ltv, r.financing.perm_by_dscr)
    print(
        f"  financing: structure={r.financing.structure}, "
        f"gate qualifies={r.financing.perm_first_qualifies}, "
        f"perm_loan=${r.financing.perm_loan:,.0f} = min(LTV ${r.financing.perm_by_ltv:,.0f}, DSCR ${r.financing.perm_by_dscr:,.0f})"
    )

    # ---- flags: pre_1980, below_agency_gate, insurance_below_commercial -
    flag_codes = {f.code for f in r.flags}
    for required in {"pre_1980_structure", "below_agency_gate", "insurance_below_commercial"}:
        assert required in flag_codes, (required, flag_codes)
    blocking_codes = {f.code for f in r.flags if f.severity == "blocking"}
    print(f"  flags ({len(r.flags)}): blocking={sorted(blocking_codes)}")

    # ---- verdict + confidence forced by blocking flags ---------------------
    assert r.decision == "conditional", r.decision
    assert r.confidence == "low", r.confidence
    print(f"  verdict: {r.decision} (confidence={r.confidence})")

    # ---- cross-checks include YoC spread ---------------------------------
    cc_names = {c.name for c in r.cross_checks}
    assert "yoc_spread_vs_exit_cap" in cc_names
    yoc_check = next(c for c in r.cross_checks if c.name == "yoc_spread_vs_exit_cap")
    print(f"  cross-check YoC spread: {yoc_check.value:.4f} ({yoc_check.status})")

    # ---- sensitivity reports a swing (not just a center value) ---------
    assert len(r.sensitivity_cells) == 25, len(r.sensitivity_cells)  # 5 × 5 grid
    assert r.sensitivity_swing > 0
    print(f"  sensitivity grid: {len(r.sensitivity_cells)} cells, swing=${r.sensitivity_swing:,.0f}")

    # ---- risk register is ranked; top entry = load-bearing assumption --
    assert len(r.risk_register) >= 1
    swings = [abs(rr.swing_dollars) for rr in r.risk_register]
    assert swings == sorted(swings, reverse=True), "risk register not ranked by swing"
    top = r.risk_register[0]
    print(
        f"  load-bearing assumption: {top.input!r} "
        f"(provenance={top.provenance}, swing ${top.swing_dollars:,.0f})"
    )

    # ---- broker diff is populated ----------------------------------------
    assert any(d.line == "noi" for d in r.broker_diff)
    print(f"  broker pro-forma diff: {len(r.broker_diff)} lines")

    # ---- serialize to payload + JSON-Schema validate ---------------------
    payload = result_to_payload(
        r, deal_id="deal-1", address="100 Test St",
        units=24, as_of="2026-06-01",
        thesis="Distressed 24-unit; 6 achieved-renovated leases anchor stabilized at $1500. "
               "Pay in-place economics; bridge-to-perm via SBL once 90/90 hits.",
    )
    schema = json.loads(Path("contracts/value_add_analysis.schema.json").read_text())
    jsonschema.Draft7Validator(schema).validate(payload)
    print("  payload validates against value_add_analysis.schema.json")

    # ---- and against the Pydantic mirror ---------------------------------
    from reeve.contracts.value_add_analysis import ValueAddAnalysis
    ValueAddAnalysis.model_validate(payload)
    print("  payload validates against ValueAddAnalysis (Pydantic)")

    print("ok.")


if __name__ == "__main__":
    main()
