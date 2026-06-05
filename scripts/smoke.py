"""Step-1 smoke check: imports + contract round-trip + audit serialization."""
import json
from pathlib import Path

import jsonschema

from reeve.audit.events import AuditEvent, AuditKind, EntityType
from reeve.contracts import DealAnalysis
from reeve.db.mongo import COLLECTIONS, INDEX_SPECS
from reeve.models import (
    AgentRun,
    Artifact,
    ArtifactType,
    Building,
    Comp,
    Confidence,
    Conversation,
    Deal,
    DealStatus,
    Investor,
    Lease,
    Message,
    MessageRole,
    Portfolio,
    Proposal,
    Tenant,
    Transaction,
    Unit,
    Vendor,
)


def _sample_deal_analysis() -> dict:
    return {
        "type": "deal_analysis",
        "address": "1423 Elmwood Ave",
        "units": 8,
        "ask": 1150000,
        "price_per_unit": 143750,
        "verdict": {
            "decision": "pursue",
            "max_price": 1060000,
            "headline": "Pursue at ≤ $1.06M",
        },
        "metrics": {
            "cap_in_place": 0.054,
            "cap_proforma": 0.069,
            "coc_year1": 0.041,
            "coc_stabilized": 0.087,
            "dscr": 1.24,
            "avg_rent_in_place": 1233,
            "avg_rent_market": 1466,
            "rent_upside_pct": 0.19,
            "rent_upside_monthly": 1866,
        },
        "rent_roll": [
            {"unit": "1A", "in_place": 1150, "market": 1450},
            {"unit": "1B", "in_place": 1100, "market": 1425},
        ],
        "assumptions": ["Vacancy 5%", "Mgmt 8%", "Taxes reassessed at sale"],
        "thesis": "Eight units running 19% under market.",
        "confidence": "medium",
        "unverified": ["rent roll dates"],
    }


def main() -> None:
    # 1) every entity instantiates with defaults filled
    investor = Investor(name="James M.", entity_name="Oakwood Holdings")
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    building = Building(portfolio_id=portfolio.id, address="1 Elmwood", units_count=8)
    unit = Unit(building_id=building.id, label="1A")
    deal = Deal(investor_id=investor.id, address="1423 Elmwood Ave", status=DealStatus.SOURCED)
    convo = Conversation(investor_id=investor.id, title="1423 Elmwood")
    msg = Message(conversation_id=convo.id, seq=1, speaker="investor",
                  role=MessageRole.USER, text="Worth a closer look?")
    run = AgentRun(conversation_id=convo.id, agent="ana", task="Underwrite 1423 Elmwood")
    artifact = Artifact(
        type=ArtifactType.DEAL_ANALYSIS, produced_by="ana", agent_run_id=run.id,
        payload=_sample_deal_analysis(), deal_id=deal.id, confidence=Confidence.MEDIUM,
    )
    stubs = [
        Lease(investor_id=investor.id, unit_id=unit.id, tenant_id="t1"),
        Tenant(investor_id=investor.id, name="Jane"),
        Vendor(investor_id=investor.id, name="ACME Plumbing"),
        Transaction(investor_id=investor.id, building_id=building.id,
                    date="2026-04-01", amount=123.45),
        Comp(area_key="07090", payload={"avg_rent": 1466}),
        Proposal(investor_id=investor.id, agent="cole", action="send_loi",
                 summary="LOI at $1.06M", payload={"price": 1060000}),
    ]

    # 2) contract: Pydantic + JSON Schema accept the same payload
    payload = _sample_deal_analysis()
    DealAnalysis.model_validate(payload)
    schema = json.loads(Path("contracts/deal_analysis.schema.json").read_text())
    jsonschema.Draft7Validator(schema).validate(payload)

    # 3) audit event serializes to a Dynamo-shaped item
    event = AuditEvent(
        investor_id=investor.id,
        actor="ana",
        kind=AuditKind.ARTIFACT,
        entity_type=EntityType.DEAL,
        entity_id=deal.id,
        detail={"artifact_id": artifact.id, "cap": 0.054},
    )
    item = event.to_item()
    assert item["investor_id"] == investor.id
    assert item["ts_event_id"].startswith(event.ts)
    assert item["kind"] == "artifact"

    # 4) index spec covers every collection
    missing = set(COLLECTIONS) - set(INDEX_SPECS)
    assert not missing, f"INDEX_SPECS missing: {missing}"

    print(
        "ok:",
        f"{len(COLLECTIONS)} collections,",
        f"{sum(len(v) for v in INDEX_SPECS.values())} indexes,",
        f"{len(stubs) + 7} entities exercised,",
        "contract round-trips,",
        "audit item shaped.",
    )


if __name__ == "__main__":
    main()
