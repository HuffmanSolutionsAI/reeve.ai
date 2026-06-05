"""Bea's tools: re-categorize transactions (ACT_INTERNAL), submit a
bookkeeping report (terminal ACT_INTERNAL), and propose adjusting entries
(GATED). The gated handler creates a manual Transaction row; the agent
loop never reaches it — only `execute_approved_proposal` does."""
from __future__ import annotations

from ...contracts.bookkeeping_report import BookkeepingReport
from ...db.mongo import COLLECTIONS, db
from ...finance.categorizer import CATEGORIES
from ...models.artifact import ArtifactType, Confidence
from ...models.base import now_iso
from ...models.stubs import Transaction
from ...repos.artifacts import write_artifact
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


_CATEGORY_NAMES = [label for label, _ in CATEGORIES] + ["other"]


@tool(
    "update_transaction_category",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "string"},
            "category": {"enum": _CATEGORY_NAMES},
            "reason": {"type": "string", "description": "Why the recategorization."},
        },
        "required": ["transaction_id", "category"],
        "additionalProperties": False,
    },
    (
        "Replace a transaction's category. Marks categorized_by='bea' and "
        "stamps categorized_at. Reversible — Bea can re-update later."
    ),
    reads=["transaction"],
    writes=["categorize_transaction"],
    needs_ctx=True,
)
async def update_transaction_category(
    transaction_id: str,
    category: str,
    reason: str | None = None,
    _ctx: RunContext | None = None,
) -> dict:
    assert _ctx is not None
    coll = db()[COLLECTIONS["transactions"]]
    result = await coll.update_one(
        {"_id": transaction_id, "investor_id": _ctx.investor_id},
        {
            "$set": {
                "category": category,
                "categorized_by": "bea",
                "categorized_at": now_iso(),
                "updated_at": now_iso(),
            }
        },
    )
    if not result.matched_count:
        return {
            "updated": False,
            "transaction_id": transaction_id,
            "reason": "transaction not found or not in scope",
        }
    return {
        "updated": True,
        "transaction_id": transaction_id,
        "category": category,
        "rationale": reason,
    }


@tool(
    "post_adjusting_entry",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "building_id": {"type": "string"},
            "date": {"type": "string", "description": "ISO date the entry applies to."},
            "amount": {
                "type": "number",
                "description": "Signed: positive = inflow, negative = outflow.",
            },
            "category": {"enum": _CATEGORY_NAMES},
            "description": {"type": "string"},
            "reason": {"type": "string", "description": "Why an adjustment is needed."},
        },
        "required": ["building_id", "date", "amount", "category", "description"],
        "additionalProperties": False,
    },
    (
        "Post a manual adjusting entry to the ledger. GATED — the runner "
        "intercepts this call from the agent loop and queues a proposal; "
        "only execute_approved_proposal writes the row, after a human "
        "approves."
    ),
    reads=[],
    writes=["post_adjusting_entry"],
)
async def post_adjusting_entry(
    building_id: str,
    date: str,
    amount: float,
    category: str,
    description: str,
    reason: str | None = None,
) -> dict:
    # The handler runs at execution time. It looks up the building to find
    # investor_id (the agent never passes ids it could derive).
    building = await db()[COLLECTIONS["buildings"]].find_one({"_id": building_id})
    if building is None:
        raise ValueError(f"building {building_id!r} not found")
    portfolio = await db()[COLLECTIONS["portfolios"]].find_one(
        {"_id": building["portfolio_id"]}
    )
    if portfolio is None:
        raise ValueError(f"portfolio {building['portfolio_id']!r} not found")
    investor_id = portfolio["investor_id"]

    txn = Transaction(
        investor_id=investor_id,
        building_id=building_id,
        date=date,
        amount=float(amount),
        category=category,
        description=f"[Adjustment] {description}",
        merchant="Manual entry (Bea)",
        reconciled=True,
        categorized_by="bea",
        categorized_at=now_iso(),
    )
    doc = txn.model_dump(by_alias=True)
    await db()[COLLECTIONS["transactions"]].insert_one(doc)
    return {
        "posted": True,
        "transaction_id": txn.id,
        "building_id": building_id,
        "category": category,
        "amount": amount,
        "reason": reason,
    }


@tool(
    "submit_bookkeeping_report",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "artifact": {
                "type": "object",
                "description": (
                    "bookkeeping_report payload matching "
                    "/contracts/bookkeeping_report.schema.json"
                ),
            },
        },
        "required": ["artifact"],
        "additionalProperties": False,
    },
    "Emit the bookkeeping_report artifact. Bea's terminal tool — call to finish.",
    reads=[],
    writes=["write_artifact"],
    terminal=True,
    needs_ctx=True,
)
async def submit_bookkeeping_report(
    artifact: dict, _ctx: RunContext | None = None,
) -> dict:
    BookkeepingReport.model_validate(artifact)
    assert _ctx is not None and _ctx.agent_run_id is not None
    written = await write_artifact(
        type=ArtifactType.BOOKKEEPING_REPORT,
        payload=artifact,
        produced_by=_ctx.agent_id or "bea",
        agent_run_id=_ctx.agent_run_id,
        confidence=Confidence(artifact["confidence"]),
        unverified=list(artifact.get("unverified", [])),
    )
    return {
        "type": "bookkeeping_report",
        "artifact_id": written.id,
        "version": written.version,
        **artifact,
    }
