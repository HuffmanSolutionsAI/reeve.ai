"""Cascade categorizer smoke: rules → LLM fallback.

Verifies:
  - In `rules` mode, ambiguous descriptions stay 'other'.
  - In `cascade` mode, the same descriptions get an LLM label via a
    mocked Anthropic client (no API key needed).
  - The LLM categorizer caches by description hash; a second sync over
    the same fixtures makes zero additional LLM calls.
  - Transactions categorized via the cascade are tagged
    categorized_by='llm_cascade'."""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

from dataclasses import dataclass
from typing import Any

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.config import settings
from reeve.finance.llm_categorizer import LLMCategorizer, set_default
from reeve.finance.plaid import MockPlaidClient, sync_transactions
from reeve.repos.transactions import list_transactions as repo_list


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    proposals_mod.set_default(None)
    return client


class _NullAudit:
    def emit(self, **kw): return None
    def write(self, e): return e
    def feed(self, *a, **k): return []
    def by_entity(self, *a, **k): return []


@dataclass
class _Block:
    type: str
    text: str | None = None


@dataclass
class _Resp:
    content: list[_Block]


class _FakeLLM:
    """Deterministic LLM stand-in. Reads the description out of the prompt
    and picks a label from a tiny hand-written rulebook. Counts calls so
    we can assert the cache works."""

    def __init__(self) -> None:
        self.messages = self
        self.call_count = 0

    async def create(self, **kw: Any) -> _Resp:
        self.call_count += 1
        prompt = kw["messages"][0]["content"].lower()
        if "boiler" in prompt or "hot water" in prompt:
            label = "maintenance"
        elif "credit card processing" in prompt or "ach fee" in prompt:
            label = "management"
        elif "snow removal" in prompt or "landscap" in prompt:
            label = "maintenance"
        elif "trash" in prompt or "garbage" in prompt:
            label = "utilities"
        else:
            label = "other"
        return _Resp([_Block("text", text=label)])


_AMBIGUOUS_FIXTURES = [
    # The rule list intentionally doesn't catch these — that's the point.
    {"plaid_id": "x-1", "account_id": "acct-b1", "date": "2026-04-02",
     "amount": -185.0, "description": "Boiler service call - second floor unit",
     "merchant": "Northeast Boiler Co", "plaid_category": ["Service"]},
    {"plaid_id": "x-2", "account_id": "acct-b1", "date": "2026-04-05",
     "amount": -28.0, "description": "Credit card processing fee - tenant portal",
     "merchant": "Stripe", "plaid_category": ["Fee"]},
    {"plaid_id": "x-3", "account_id": "acct-b1", "date": "2026-04-12",
     "amount": -310.0, "description": "Snow removal April storm",
     "merchant": "WinterScape", "plaid_category": ["Service"]},
    {"plaid_id": "x-4", "account_id": "acct-b1", "date": "2026-04-15",
     "amount": -120.0, "description": "Trash collection monthly",
     "merchant": "City Waste", "plaid_category": ["Service"]},
]


async def _run_sync() -> int:
    client = MockPlaidClient(fixtures=_AMBIGUOUS_FIXTURES)
    ptxns = client.fetch_transactions("acct-b1", "1970-01-01", "9999-12-31")
    return await sync_transactions(
        investor_id="inv-1", building_id="bldg-1", plaid_txns=ptxns,
    )


async def main() -> None:
    print("categorizer smoke (rules → LLM cascade):")
    install_mock_db()
    audit_mod.set_default(_NullAudit())

    # ---- 1) Rules-only: ambiguous descriptions stay 'other' --------------
    settings.categorizer = "rules"
    await _run_sync()
    rows = await repo_list(investor_id="inv-1", period_start="1970-01-01", period_end="9999-12-31")
    by_cat = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    assert by_cat.get("other", 0) == len(_AMBIGUOUS_FIXTURES), by_cat
    print(f"  rules-only: {by_cat.get('other', 0)} 'other' (all {len(_AMBIGUOUS_FIXTURES)} fixtures)")

    # Reset Mongo for the cascade run (plaid_id upsert would otherwise
    # leave the rules-tagged rows in place).
    install_mock_db()
    audit_mod.set_default(_NullAudit())

    # ---- 2) Cascade: LLM categorizer assigns real labels -----------------
    settings.categorizer = "cascade"
    fake = _FakeLLM()
    set_default(LLMCategorizer(llm=fake))
    await _run_sync()
    rows = await repo_list(investor_id="inv-1", period_start="1970-01-01", period_end="9999-12-31")
    by_cat = {}
    by_tag = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        by_tag[r["categorized_by"]] = by_tag.get(r["categorized_by"], 0) + 1
    assert by_cat.get("other", 0) == 0, by_cat
    assert by_cat.get("maintenance", 0) == 2, by_cat   # boiler + snow
    assert by_cat.get("management", 0) == 1, by_cat    # cc fee
    assert by_cat.get("utilities", 0) == 1, by_cat     # trash
    assert by_tag.get("llm_cascade", 0) == len(_AMBIGUOUS_FIXTURES), by_tag
    assert fake.call_count == len(_AMBIGUOUS_FIXTURES), fake.call_count
    print(f"  cascade: {by_cat} (categorized_by={by_tag})")
    print(f"  LLM calls: {fake.call_count} (one per unique description)")

    # ---- 3) Cache: re-sync the same fixtures, LLM call count unchanged ---
    await _run_sync()
    assert fake.call_count == len(_AMBIGUOUS_FIXTURES), fake.call_count
    print(f"  cache: re-sync added 0 LLM calls (still {fake.call_count})")

    settings.categorizer = "rules"
    set_default(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
