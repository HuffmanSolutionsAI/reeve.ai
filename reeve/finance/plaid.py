"""Plaid client interface + dev mock + sync function.

`PlaidClient` is the protocol every implementation honors. The real client
wraps the official `plaid-python` SDK; `MockPlaidClient` reads from a
fixture list so smoke tests and the seed script can drive the same code
path. `sync_transactions` is the only function callers need."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from ..models.base import now_iso
from ..models.stubs import Transaction
from ..repos.transactions import insert_transactions
from .categorizer import categorize_async


@dataclass
class PlaidTransaction:
    plaid_id: str
    account_id: str
    date: str
    amount: float  # signed: positive = inflow, negative = outflow
    description: str = ""
    merchant: str | None = None
    plaid_category: list[str] = field(default_factory=list)


class PlaidClient(Protocol):
    def fetch_transactions(
        self, account_id: str, since: str, until: str
    ) -> list[PlaidTransaction]: ...


@dataclass
class MockPlaidClient:
    fixtures: list[dict] = field(default_factory=list)

    def fetch_transactions(
        self, account_id: str, since: str, until: str
    ) -> list[PlaidTransaction]:
        out: list[PlaidTransaction] = []
        for t in self.fixtures:
            if t.get("account_id") != account_id:
                continue
            if not (since <= t["date"] <= until):
                continue
            out.append(PlaidTransaction(
                plaid_id=t["plaid_id"],
                account_id=t["account_id"],
                date=t["date"],
                amount=float(t["amount"]),
                description=t.get("description", ""),
                merchant=t.get("merchant"),
                plaid_category=list(t.get("plaid_category") or []),
            ))
        return out


async def sync_transactions(
    *,
    investor_id: str,
    building_id: str,
    plaid_txns: Iterable[PlaidTransaction],
) -> int:
    """Categorize Plaid rows and upsert into Mongo by plaid_id (idempotent).

    Categorization honors `settings.categorizer`:
      - 'rules'   — regex only (default).
      - 'cascade' — regex; LLM fallback for rows the regex marks `other`.
    The `categorized_by` field reflects which path tagged the row."""
    from ..config import settings
    txns: list[Transaction] = []
    ts = now_iso()
    strategy = (settings.categorizer or "rules").lower()
    for p in plaid_txns:
        cat = await categorize_async(p.description, plaid_categories=p.plaid_category)
        # Rough labeling: if cascade is on and rules would've said other,
        # the cascade may have escalated to LLM. We don't re-run rules; we
        # just tag the row with the active strategy.
        labeled_by = (
            "llm_cascade" if strategy == "cascade" and cat != "other" and _was_llm(p, cat)
            else "rule_based"
        )
        txns.append(Transaction(
            investor_id=investor_id,
            building_id=building_id,
            account_id=p.account_id,
            plaid_id=p.plaid_id,
            date=p.date,
            amount=p.amount,
            description=p.description,
            merchant=p.merchant,
            category=cat,
            plaid_category=list(p.plaid_category),
            reconciled=False,
            categorized_by=labeled_by,
            categorized_at=ts,
        ))
    return await insert_transactions(txns)


def _was_llm(p: PlaidTransaction, cat: str) -> bool:
    """True iff the rule-based pass would have returned 'other' (meaning the
    cascade had to fall through to the LLM)."""
    from .categorizer import categorize
    return categorize(p.description, plaid_categories=p.plaid_category) == "other" and cat != "other"
