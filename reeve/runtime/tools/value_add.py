"""Ana v2 tools: get the deal's v2 inputs, run the engine, submit the
value_add_analysis artifact.

Three tools:
  get_deal_underwriting_inputs — Ana fetches the embedded entities + the
    active rent roll + active operating statement from one call. Sensitive
    reads on the rent roll (per-unit lease detail) and the operating
    statement (financial data), so the audit fires on each call.
  run_value_add_analysis — pure invocation of the engine. Ana passes a
    candidate bid; the tool returns the result dict for Ana to reason
    about before submitting.
  submit_value_add_analysis — terminal. Validates against the contract,
    writes a versioned VALUE_ADD_ANALYSIS artifact, advances the deal's
    latest_analysis_id."""
from __future__ import annotations

from typing import Any

from ...contracts.value_add_analysis import ValueAddAnalysis
from ...db.mongo import COLLECTIONS, db
from ...models.artifact import ArtifactType, Confidence
from ...models.deal import DealStatus
from ...models.underwriting import (
    BrokerProforma,
    DealAssumptions,
    FinancingScenario,
    MarketContext,
    PropertyProfile,
    RenovationBudget,
)
from ...repos.artifacts import write_artifact
from ...repos.deals import get_deal, set_deal_status
from ...repos.operating_statements import get_operating_statement
from ...repos.rent_rolls import get_rent_roll
from ...underwriting.value_add import analyze
from ...underwriting.value_add.payload import result_to_payload
from ...underwriting.value_add.runner import AnalysisInputs
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


_DECISION_TO_STATUS = {
    "pursue": DealStatus.PURSUE,
    "pass": DealStatus.PASS,
    "conditional": DealStatus.ANALYZED,
}


@tool(
    "get_deal_underwriting_inputs",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
        },
        "required": ["deal_id"],
        "additionalProperties": False,
    },
    (
        "Return the deal's v2 underwriting bundle: profile, embedded "
        "PropertyProfile / RenovationBudget / MarketContext / "
        "FinancingScenario[] / DealAssumptions / BrokerProforma, plus the "
        "ACTIVE rent_roll and operating_statement linked via "
        "deal.active_*_id. Sensitive reads on lease + transaction-shaped "
        "data; every call audits."
    ),
    reads=["deal", "lease", "transaction"],
    needs_ctx=True,
)
async def get_deal_underwriting_inputs(deal_id: str, _ctx: RunContext) -> dict:
    deal = await get_deal(deal_id)
    if deal is None or deal.investor_id != _ctx.investor_id:
        return {"found": False, "reason": "deal not found"}

    rr_id = deal.active_rent_roll_id
    op_id = deal.active_operating_statement_id
    rent_roll = await get_rent_roll(rr_id) if rr_id else None
    opex = await get_operating_statement(op_id) if op_id else None

    missing: list[str] = []
    if rent_roll is None:
        missing.append("active_rent_roll")
    elif not rent_roll.human_confirmed:
        missing.append("rent_roll_unconfirmed")
    if opex is None:
        missing.append("active_operating_statement")
    elif not opex.human_confirmed:
        missing.append("operating_statement_unconfirmed")
    if deal.property_profile is None:
        missing.append("property_profile")
    if deal.renovation_budget is None:
        missing.append("renovation_budget")
    if deal.market_context is None:
        missing.append("market_context")
    if not deal.financing_scenarios:
        missing.append("financing_scenarios")
    if deal.assumptions is None:
        missing.append("assumptions")

    return {
        "found": True,
        "deal_id": deal.id,
        "address": deal.address,
        "profile": deal.profile,
        "ask": deal.ask,
        "units": deal.units,
        "property_profile": deal.property_profile.model_dump() if deal.property_profile else None,
        "renovation_budget": deal.renovation_budget.model_dump() if deal.renovation_budget else None,
        "market_context": deal.market_context.model_dump() if deal.market_context else None,
        "financing_scenarios": [f.model_dump() for f in deal.financing_scenarios],
        "assumptions": deal.assumptions.model_dump() if deal.assumptions else None,
        "broker_proforma": deal.broker_proforma.model_dump() if deal.broker_proforma else None,
        "rent_roll": rent_roll.model_dump() if rent_roll else None,
        "operating_statement": opex.model_dump() if opex else None,
        "missing": missing,
    }


@tool(
    "run_value_add_analysis",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "bid_price": {"type": "number", "minimum": 0,
                          "description": "Candidate bid; flows into tax reassessment + DSCR. If 0, uses the deal's ask."},
            "financing_scenario_index": {"type": "integer", "minimum": 0,
                                         "description": "Which financing scenario to size (default 0)."},
        },
        "required": ["deal_id"],
        "additionalProperties": False,
    },
    (
        "Pure invocation of the v2 underwriting engine. Returns the full "
        "result dict (three NOI states + broker diff, valuation band, "
        "cost-to-stabilize, financing sizing, cross-checks, sensitivity "
        "grid, risk register, flags). Ana uses this to reason BEFORE "
        "calling submit_value_add_analysis."
    ),
    reads=["deal", "lease", "transaction"],
    needs_ctx=True,
)
async def run_value_add_analysis(
    deal_id: str,
    _ctx: RunContext,
    bid_price: float = 0.0,
    financing_scenario_index: int = 0,
) -> dict:
    deal = await get_deal(deal_id)
    if deal is None or deal.investor_id != _ctx.investor_id:
        return {"ok": False, "reason": "deal not found"}

    # Validate the bundle is complete.
    rr = await get_rent_roll(deal.active_rent_roll_id) if deal.active_rent_roll_id else None
    opex = await get_operating_statement(deal.active_operating_statement_id) if deal.active_operating_statement_id else None
    if not (
        rr and opex and deal.renovation_budget and deal.market_context
        and deal.financing_scenarios and deal.assumptions
    ):
        return {
            "ok": False,
            "reason": "missing inputs; call get_deal_underwriting_inputs and surface what's missing",
        }
    if not (0 <= financing_scenario_index < len(deal.financing_scenarios)):
        return {"ok": False, "reason": f"financing_scenario_index out of range"}

    bid = bid_price or deal.ask or 0.0
    if bid <= 0:
        return {"ok": False, "reason": "bid_price required (deal has no ask)"}

    inputs = AnalysisInputs(
        rent_roll=rr, opex=opex, profile=deal.property_profile,
        budget=deal.renovation_budget, market=deal.market_context,
        financing=deal.financing_scenarios[financing_scenario_index],
        assumptions=deal.assumptions, broker_proforma=deal.broker_proforma,
        bid_price=bid,
    )
    result = analyze(inputs)
    payload = result_to_payload(
        result,
        deal_id=deal.id, address=deal.address, units=deal.units or 1,
        as_of=rr.as_of,
    )
    return {"ok": True, "bid_used": bid, "result": payload}


@tool(
    "submit_value_add_analysis",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": "value_add_analysis payload matching /contracts/value_add_analysis.schema.json",
            },
            "deal_id": {"type": "string"},
        },
        "required": ["artifact", "deal_id"],
        "additionalProperties": False,
    },
    (
        "Emit the value_add_analysis artifact. Ana's v2 terminal tool. "
        "Validates against the contract, writes a versioned artifact, "
        "and advances the deal's latest_analysis_id + status to match "
        "the verdict. Like submit_deal_analysis, but for the value-add "
        "contract."
    ),
    reads=[],
    writes=["write_artifact", "set_deal_status"],
    terminal=True,
    needs_ctx=True,
)
async def submit_value_add_analysis(
    artifact: dict,
    deal_id: str,
    _ctx: RunContext | None = None,
) -> dict:
    ValueAddAnalysis.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None

    # Versioning: if the deal already has an analysis, the new one supersedes.
    existing = await get_deal(deal_id)
    if existing is None:
        return {"submitted": False, "reason": "deal not found"}
    supersedes = existing.latest_analysis_id

    written = await write_artifact(
        type=ArtifactType.VALUE_ADD_ANALYSIS,
        payload=artifact,
        produced_by=_ctx.agent_id or "ana",
        agent_run_id=_ctx.agent_run_id,
        deal_id=deal_id,
        confidence=Confidence(artifact["confidence"]),
        assumptions=[],   # captured inside the payload's risk register
        unverified=list(artifact.get("unverified", [])),
        supersedes=supersedes,
    )
    decision = artifact["verdict"]["decision"]
    await set_deal_status(
        deal_id,
        _DECISION_TO_STATUS.get(decision, DealStatus.ANALYZED),
        latest_analysis_id=written.id,
    )
    return {
        "type": "value_add_analysis",
        "artifact_id": written.id,
        "version": written.version,
        "supersedes": supersedes,
        **artifact,
    }
