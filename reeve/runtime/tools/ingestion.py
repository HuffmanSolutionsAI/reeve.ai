"""Chat-entry ingestion tools (Ana).

The investor provides deal data in chat (pasted rent roll, T-12 numbers,
reno scope, financing terms); the agent parses it into these tools'
structured inputs. Three hard rules from the data-model doc §8:

  1. Staged documents are born with human_confirmed=False. These tools
     have NO parameter to set it — promotion to active happens only via
     the investor-authenticated confirm endpoints
     (POST /api/rent-rolls/{id}/confirm and
      POST /api/operating-statements/{id}/confirm).
  2. Machine validation runs at ingest and is stored on the record; a
     failed check doesn't block ingest, it blocks confidence.
  3. Money fields default to `broker_claimed` provenance. The agent may
     pass provenance='verified' ONLY when the investor explicitly says
     the numbers come from their own records/audit.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ...db.mongo import COLLECTIONS, db
from ...ingestion import validate_operating_statement, validate_rent_roll
from ...models.base import now_iso
from ...models.underwriting import (
    BrokerProforma,
    DealAssumptions,
    FinancingScenario,
    IngestFormat,
    InsuranceRecord,
    LeaseRow,
    MarketContext,
    OperatingLine,
    OperatingPeriod,
    OperatingStatement,
    PropertyProfile,
    Provenance,
    RenovationBudget,
    RentRoll,
    RentRollSource,
    Sourced,
    TaxRecord,
    UtilityRecord,
)
from ...repos.deals import get_deal
from ...repos.operating_statements import insert_operating_statement
from ...repos.rent_rolls import insert_rent_roll
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


def _sourced(value: float | None, prov: str) -> dict | None:
    if value is None:
        return None
    return {"value": value, "prov": prov}


async def _owned_deal(deal_id: str, investor_id: str):
    deal = await get_deal(deal_id)
    if deal is None or deal.investor_id != investor_id:
        return None
    return deal


# --------------------------------------------------------------------------
@tool(
    "update_deal_underwriting",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "profile": {"enum": ["stabilized", "value_add", "distressed"]},
            "property_profile": {
                "type": "object",
                "description": "PropertyProfile object: structures[] (label, structure_type, year_built, units_count), unit_mix[], physical_occupancy {value, prov}, condition_inventory {renovated, rent_ready, down}, completed_capital[], site, submarket, demand_drivers[].",
            },
            "renovation_budget": {
                "type": "object",
                "description": "RenovationBudget object: tiers[] (condition_tier, scope_description, cost_per_unit {value, prov}, units_count), make_ready_per_unit, systems[], abatement {amount, basis, tested}, contingency_pct, closing_costs_pct.",
            },
            "market_context": {
                "type": "object",
                "description": "MarketContext object: rent_comps[] (condition, beds, baths, rent), cap_rates {class_a/b/c}, asset_class, vacancy_norm {value, prov}, rent_growth_trend.",
            },
            "financing_scenarios": {
                "type": "array",
                "items": {"type": "object"},
                "description": "FULL-LIST REPLACE of FinancingScenario objects: label, bridge {ltc, rate, term_months, expected_hold_months}, perm {program, rate, amort_years, min_dscr, max_ltv, occupancy_gate {occupancy, days}, refi_costs_pct}.",
            },
            "assumptions": {
                "type": "object",
                "description": "DealAssumptions object: target_rents[] (condition_tier or unit_mix_beds, monthly_rent, rationale), exit_cap, required_margin {margin_type, value}, stabilized_vacancy, credit_loss, lease_up_months, ancillary[] (item, monthly, basis).",
            },
            "broker_proforma": {
                "type": "object",
                "description": "BrokerProforma: asking_price, asking_cap, asking_noi, rent_assumption_per_unit, opex_assumption_annual, source. Stored verbatim as adversarial input.",
            },
        },
        "required": ["deal_id"],
        "additionalProperties": False,
    },
    (
        "Patch the deal's v2 underwriting bundle. Partial — only the fields "
        "passed are written; financing_scenarios is a full-list replace. "
        "Each entity is validated against its schema; on a validation error "
        "the tool returns the error text so the agent can fix the shape and "
        "retry. Use this when the investor describes the property, the reno "
        "scope, the financing terms, or the assumptions in chat."
    ),
    reads=["deal"],
    writes=["update_deal_underwriting"],
    needs_ctx=True,
)
async def update_deal_underwriting(
    deal_id: str,
    _ctx: RunContext,
    profile: str | None = None,
    property_profile: dict | None = None,
    renovation_budget: dict | None = None,
    market_context: dict | None = None,
    financing_scenarios: list[dict] | None = None,
    assumptions: dict | None = None,
    broker_proforma: dict | None = None,
) -> dict:
    deal = await _owned_deal(deal_id, _ctx.investor_id)
    if deal is None:
        return {"updated": False, "reason": "deal not found"}

    updates: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def _try(field: str, model_cls, payload):
        if payload is None:
            return
        try:
            validated = model_cls.model_validate(payload)
            updates[field] = validated.model_dump()
        except ValidationError as e:
            errors[field] = str(e)

    if profile is not None:
        updates["profile"] = profile
    _try("property_profile", PropertyProfile, property_profile)
    _try("renovation_budget", RenovationBudget, renovation_budget)
    _try("market_context", MarketContext, market_context)
    _try("assumptions", DealAssumptions, assumptions)
    _try("broker_proforma", BrokerProforma, broker_proforma)
    if financing_scenarios is not None:
        try:
            validated = [FinancingScenario.model_validate(f) for f in financing_scenarios]
            updates["financing_scenarios"] = [f.model_dump() for f in validated]
        except ValidationError as e:
            errors["financing_scenarios"] = str(e)

    if errors:
        return {"updated": False, "validation_errors": errors}
    if not updates:
        return {"updated": False, "reason": "no fields to update"}

    updates["updated_at"] = now_iso()
    await db()[COLLECTIONS["deals"]].update_one({"_id": deal_id}, {"$set": updates})
    return {
        "updated": True,
        "deal_id": deal_id,
        "changed": sorted(k for k in updates if k != "updated_at"),
    }


# --------------------------------------------------------------------------
_LEASE_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "unit_label": {"type": "string"},
        "condition_tier": {"enum": ["renovated", "rent_ready", "down"]},
        "occupied": {"type": "boolean"},
        "in_place_rent": {"type": "number"},
        "achieved_rent": {
            "type": "number",
            "description": "ONLY for renovated+occupied units — the signed lease at the post-reno standard.",
        },
        "asking_rent": {"type": "number"},
        "lease_start": {"type": "string"},
        "lease_end": {"type": "string"},
        "concessions": {"type": "number"},
        "delinquent_balance": {"type": "number"},
        "notes": {"type": "string"},
    },
    "required": ["unit_label", "condition_tier", "occupied"],
    "additionalProperties": False,
}


@tool(
    "ingest_rent_roll",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "as_of": {"type": "string", "description": "ISO date of the snapshot."},
            "leases": {"type": "array", "items": _LEASE_ROW_SCHEMA, "minItems": 1},
            "provenance": {
                "enum": ["verified", "broker_claimed"],
                "description": "Where the money figures came from. 'verified' ONLY when the investor explicitly says the roll is from their own records/audit. Default broker_claimed.",
            },
            "source_description": {"type": "string", "description": "e.g. 'pasted into chat from OM PDF p.12'"},
            "claimed_unit_count": {"type": "integer", "description": "What the document claims about itself — used by machine validation."},
            "claimed_occupancy": {"type": "number"},
            "stated_monthly_total": {"type": "number"},
        },
        "required": ["deal_id", "as_of", "leases"],
        "additionalProperties": False,
    },
    (
        "Write a STAGED rent roll from lease rows the agent parsed out of "
        "the investor's chat message or document. Machine validation runs "
        "at ingest and is stored on the record. The roll is born "
        "UNCONFIRMED — only the investor can confirm it (Approvals screen); "
        "this tool cannot activate it. Pass the document's own claimed "
        "totals so validation can check the extraction against them."
    ),
    reads=["deal"],
    writes=["ingest_document"],
    needs_ctx=True,
)
async def ingest_rent_roll(
    deal_id: str,
    as_of: str,
    leases: list[dict],
    _ctx: RunContext,
    provenance: str = "broker_claimed",
    source_description: str | None = None,
    claimed_unit_count: int | None = None,
    claimed_occupancy: float | None = None,
    stated_monthly_total: float | None = None,
) -> dict:
    deal = await _owned_deal(deal_id, _ctx.investor_id)
    if deal is None:
        return {"ingested": False, "reason": "deal not found"}

    rows: list[LeaseRow] = []
    row_errors: list[str] = []
    for i, raw in enumerate(leases):
        payload = {
            "unit_label": raw["unit_label"],
            "condition_tier": raw["condition_tier"],
            "occupied": raw["occupied"],
            "in_place_rent": _sourced(raw.get("in_place_rent"), provenance),
            "achieved_rent": _sourced(raw.get("achieved_rent"), provenance),
            "asking_rent": _sourced(raw.get("asking_rent"), Provenance.BROKER_CLAIMED.value),
            "lease_start": raw.get("lease_start"),
            "lease_end": raw.get("lease_end"),
            "concessions": raw.get("concessions", 0.0),
            "delinquent_balance": raw.get("delinquent_balance", 0.0),
            "notes": raw.get("notes"),
        }
        try:
            rows.append(LeaseRow.model_validate(payload))
        except ValidationError as e:
            row_errors.append(f"row {i} ({raw.get('unit_label', '?')}): {e.errors()[0].get('msg', str(e))}")

    if row_errors:
        return {"ingested": False, "row_errors": row_errors}

    prior = deal.active_rent_roll_id
    rr = RentRoll(
        deal_id=deal_id,
        investor_id=_ctx.investor_id,
        as_of=as_of,
        leases=rows,
        source=RentRollSource(
            format=IngestFormat.MANUAL,
            ingested_at=now_iso(),
            extraction_method=source_description or "chat",
        ),
        supersedes=prior,
        # human_confirmed stays False — structurally not settable here.
    )
    rr.validation = validate_rent_roll(
        rr,
        claimed_unit_count=claimed_unit_count,
        claimed_occupancy=claimed_occupancy,
        stated_monthly_total=stated_monthly_total,
    )
    await insert_rent_roll(rr)

    failed = [c for c in rr.validation.checks if not c.passed]
    return {
        "ingested": True,
        "rent_roll_id": rr.id,
        "human_confirmed": False,
        "derived": rr.derived.model_dump(),
        "validation": {
            "all_passed": rr.validation.all_passed,
            "failed": [{"name": c.name, "detail": c.detail} for c in failed],
        },
        "next_step": (
            "The investor must review and confirm this rent roll on the "
            "Approvals screen before it becomes active for underwriting."
        ),
    }


# --------------------------------------------------------------------------
_OPEX_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"enum": [
            "taxes", "insurance", "utilities_water", "utilities_electric",
            "utilities_gas", "utilities_trash", "mgmt_fee",
            "repairs_maintenance", "turns", "payroll", "admin",
            "marketing", "other",
        ]},
        "annual": {"type": "number"},
        "label": {"type": "string"},
        "monthly": {"type": "array", "items": {"type": "number"},
                    "minItems": 12, "maxItems": 12},
    },
    "required": ["category", "annual"],
    "additionalProperties": False,
}


@tool(
    "ingest_operating_statement",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "period_start": {"type": "string"},
            "period_end": {"type": "string"},
            "lines": {"type": "array", "items": _OPEX_LINE_SCHEMA, "minItems": 1},
            "provenance": {"enum": ["verified", "broker_claimed"]},
            "tax": {
                "type": "object",
                "properties": {
                    "current_assessed": {"type": "number"},
                    "current_annual_bill": {"type": "number"},
                    "millage_rate": {"type": "number", "description": "Effective rate so taxes can be reassessed at any bid (millage × price)."},
                    "reassessment_estimate_at_price": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "insurance": {
                "type": "object",
                "properties": {
                    "current_annual": {"type": "number"},
                    "commercial_quote": {"type": "number"},
                    "quote_source": {"enum": ["bound_commercial", "indicated_commercial", "residential_proxy", "seller_current"]},
                },
                "additionalProperties": False,
            },
            "utilities": {
                "type": "object",
                "properties": {
                    "master_metered": {"type": "array", "items": {"type": "string"}},
                    "sub_metered": {"type": "array", "items": {"type": "string"}},
                    "owner_paid_annual": {"type": "number"},
                    "rubs_candidate": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            "reserves_per_door": {"type": "number"},
            "source_description": {"type": "string"},
            "stated_annual_total": {"type": "number", "description": "The document's own total — machine validation compares the line sum against it."},
        },
        "required": ["deal_id", "period_start", "period_end", "lines"],
        "additionalProperties": False,
    },
    (
        "Write a STAGED operating statement (T-12) from line items the "
        "agent parsed out of chat or a document. Same lifecycle as "
        "ingest_rent_roll: machine-validated at write, born UNCONFIRMED, "
        "investor confirms on the Approvals screen. Pass millage_rate "
        "when known so taxes can be reassessed per-bid in the sensitivity "
        "grid."
    ),
    reads=["deal"],
    writes=["ingest_document"],
    needs_ctx=True,
)
async def ingest_operating_statement(
    deal_id: str,
    period_start: str,
    period_end: str,
    lines: list[dict],
    _ctx: RunContext,
    provenance: str = "broker_claimed",
    tax: dict | None = None,
    insurance: dict | None = None,
    utilities: dict | None = None,
    reserves_per_door: float = 300.0,
    source_description: str | None = None,
    stated_annual_total: float | None = None,
) -> dict:
    deal = await _owned_deal(deal_id, _ctx.investor_id)
    if deal is None:
        return {"ingested": False, "reason": "deal not found"}

    try:
        op_lines = [
            OperatingLine.model_validate({
                "category": raw["category"],
                "label": raw.get("label"),
                "annual": _sourced(raw["annual"], provenance),
                "monthly": raw.get("monthly"),
            })
            for raw in lines
        ]
        tax_rec = TaxRecord.model_validate({
            "current_assessed": _sourced((tax or {}).get("current_assessed"), provenance),
            "current_annual_bill": _sourced((tax or {}).get("current_annual_bill"), provenance),
            "reassessment_estimate_at_price": _sourced(
                (tax or {}).get("reassessment_estimate_at_price"), "assumed",
            ),
            "reassessment_method": "millage_at_price" if (tax or {}).get("millage_rate") else None,
            "millage_rate": (tax or {}).get("millage_rate"),
        })
        ins_rec = InsuranceRecord.model_validate({
            "current_annual": _sourced((insurance or {}).get("current_annual"), provenance),
            "commercial_quote": _sourced((insurance or {}).get("commercial_quote"), "verified"),
            "quote_source": (insurance or {}).get("quote_source"),
        })
        util_rec = UtilityRecord.model_validate(utilities or {})
    except ValidationError as e:
        return {"ingested": False, "validation_errors": str(e)}

    prior = deal.active_operating_statement_id
    opex = OperatingStatement(
        deal_id=deal_id,
        investor_id=_ctx.investor_id,
        period=OperatingPeriod(start=period_start, end=period_end),
        lines=op_lines,
        tax=tax_rec,
        insurance=ins_rec,
        utilities=util_rec,
        reserves_per_door=reserves_per_door,
        source=RentRollSource(
            format=IngestFormat.MANUAL,
            ingested_at=now_iso(),
            extraction_method=source_description or "chat",
        ),
        supersedes=prior,
    )
    opex.validation = validate_operating_statement(
        opex, stated_annual_total=stated_annual_total,
    )
    await insert_operating_statement(opex)

    failed = [c for c in opex.validation.checks if not c.passed]
    return {
        "ingested": True,
        "operating_statement_id": opex.id,
        "human_confirmed": False,
        "annual_total": round(sum(line.annual.value for line in op_lines), 2),
        "validation": {
            "all_passed": opex.validation.all_passed,
            "failed": [{"name": c.name, "detail": c.detail} for c in failed],
        },
        "next_step": (
            "The investor must review and confirm this T-12 on the "
            "Approvals screen before it becomes active for underwriting."
        ),
    }
