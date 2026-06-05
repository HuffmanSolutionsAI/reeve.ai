"""Tess's tools: estimate annual tax liability from the ledger + portfolio,
submit a tax memo (terminal ACT_INTERNAL), or queue a filing submission
(GATED — only execute_approved_proposal touches IRS/state submission APIs).

The estimator is intentionally first-order: rental income − operating
expenses − straight-line 27.5y depreciation, taxed at federal + state
marginal rates. It surfaces every assumption so the investor (and their
real CPA) can adjust before signing anything off."""
from __future__ import annotations

from ...contracts.tax_memo import TaxMemo
from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...repos.artifacts import write_artifact
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


DEFAULT_FEDERAL_RATE = 0.24
DEFAULT_STATE_RATE = 0.06
DEFAULT_DEPRECIATION_YEARS = 27.5


@tool(
    "estimate_liability",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "gross_rental_income": {"type": "number"},
            "operating_expenses": {"type": "number"},
            "building_basis": {
                "type": "number",
                "description": "Sum of basis across buildings; drives straight-line depreciation.",
            },
            "depreciation_years": {
                "type": "number",
                "description": "Default 27.5 (residential). Use 39 for non-residential.",
            },
            "federal_rate": {"type": "number"},
            "state_rate": {"type": "number"},
        },
        "required": ["gross_rental_income", "operating_expenses", "building_basis"],
        "additionalProperties": False,
    },
    (
        "Compute a first-order federal + state tax estimate from rental "
        "income, operating expenses, and the depreciable basis. Pure "
        "computation — no IO, no scope reads. Tess uses it once she's "
        "pulled the period's transactions + portfolio basis."
    ),
    reads=[],
)
def estimate_liability(
    gross_rental_income: float,
    operating_expenses: float,
    building_basis: float,
    depreciation_years: float = DEFAULT_DEPRECIATION_YEARS,
    federal_rate: float = DEFAULT_FEDERAL_RATE,
    state_rate: float = DEFAULT_STATE_RATE,
) -> dict:
    depreciation = building_basis / depreciation_years if depreciation_years > 0 else 0.0
    net = gross_rental_income - operating_expenses - depreciation
    federal_liability = max(0.0, net * federal_rate)
    state_liability = max(0.0, net * state_rate)
    return {
        "gross_rental_income": round(gross_rental_income, 2),
        "operating_expenses": round(operating_expenses, 2),
        "depreciation": round(depreciation, 2),
        "net_rental_income": round(net, 2),
        "federal_rate": federal_rate,
        "state_rate": state_rate,
        "federal_liability": round(federal_liability, 2),
        "state_liability": round(state_liability, 2),
        "total_liability": round(federal_liability + state_liability, 2),
    }


@tool(
    "submit_tax_memo",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": (
                    "tax_memo payload matching /contracts/tax_memo.schema.json"
                ),
            },
        },
        "required": ["artifact"],
        "additionalProperties": False,
    },
    "Emit the tax_memo artifact. Tess's terminal tool — call to finish.",
    reads=[],
    writes=["write_artifact"],
    terminal=True,
    needs_ctx=True,
)
async def submit_tax_memo(
    artifact: dict, _ctx: RunContext | None = None,
) -> dict:
    TaxMemo.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None
    written = await write_artifact(
        type=ArtifactType.TAX_MEMO,
        payload=artifact,
        produced_by=_ctx.agent_id or "tess",
        agent_run_id=_ctx.agent_run_id,
        confidence=Confidence(artifact["confidence"]),
        unverified=list(artifact.get("unverified", [])),
    )
    return {
        "type": "tax_memo",
        "artifact_id": written.id,
        "version": written.version,
        **artifact,
    }


@tool(
    "submit_tax_filing",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "jurisdiction": {"enum": ["federal", "state"]},
            "form": {"type": "string", "description": "e.g. '1040 Schedule E', 'NJ-1040'"},
            "tax_year": {"type": "integer", "minimum": 2000, "maximum": 2100},
            "memo_artifact_id": {"type": "string"},
            "payment_amount": {"type": "number"},
            "filer_name": {"type": "string"},
        },
        "required": ["jurisdiction", "form", "tax_year", "memo_artifact_id"],
        "additionalProperties": False,
    },
    (
        "Submit a tax filing to the relevant jurisdiction. GATED — the "
        "runner intercepts and queues a proposal; only "
        "execute_approved_proposal runs this handler, after a human "
        "approves. The handler 'submits' (mocked in dev) and writes a "
        "tax_memo artifact tagged as the filing record."
    ),
    reads=[],
    writes=["submit_tax_filing"],
)
async def submit_tax_filing(
    jurisdiction: str,
    form: str,
    tax_year: int,
    memo_artifact_id: str,
    payment_amount: float | None = None,
    filer_name: str | None = None,
) -> dict:
    # Production path: integrate with the filer's CPA software (Drake,
    # ProConnect, TurboTax Self-Employed) or the jurisdiction's e-file API.
    # Mocked here — write a filing record artifact for the audit trail.
    submitted_at = now_iso()
    payload = {
        "type": "tax_filing_record",
        "jurisdiction": jurisdiction,
        "form": form,
        "tax_year": tax_year,
        "memo_artifact_id": memo_artifact_id,
        "payment_amount": payment_amount,
        "filer_name": filer_name,
        "submitted_at": submitted_at,
    }
    artifact = await write_artifact(
        type=ArtifactType.TAX_MEMO,
        payload=payload,
        produced_by="tess",
        agent_run_id="execution_layer",
        confidence=Confidence.HIGH,
    )
    return {
        "submitted": True,
        "submitted_at": submitted_at,
        "jurisdiction": jurisdiction,
        "form": form,
        "tax_year": tax_year,
        "artifact_id": artifact.id,
    }
