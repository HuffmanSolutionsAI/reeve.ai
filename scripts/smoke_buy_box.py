"""Smoke for Reeve's update_buy_box tool.

Verifies:
  - Loader accepts the new tool + scope.
  - Reeve patches only the fields the LLM passed; other buy-box fields are
    untouched (atomic Mongo $set on buy_box.*).
  - Audit captures act_internal on the right scope.
  - Re-reading the investor through get_investor sees the new values."""
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
from reeve.models import BuyBox, Investor
from reeve.repos.investors import get_investor, upsert_investor
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


def install_mock_audit() -> _InMemoryAudit:
    sink = _InMemoryAudit()
    audit_mod.set_default(sink)
    return sink


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


async def main() -> None:
    print("smoke_buy_box:")
    install_mock_db()
    audit = install_mock_audit()

    # Seed an investor with all six buy-box fields set, so we can confirm
    # only the ones the LLM passes get rewritten.
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(
            cap_floor=0.07, min_dscr=1.20, target_coc=0.08,
            markets=["Westfield, NJ", "Summit, NJ", "Columbus, OH"],
            unit_range=None, price_range=None,
        ),
    )
    await upsert_investor(investor)
    pre = await get_investor(investor.id)
    assert pre.buy_box.unit_range is None and pre.buy_box.price_range is None
    print(
        f"  seed buy-box: cap_floor={pre.buy_box.cap_floor}, "
        f"min_dscr={pre.buy_box.min_dscr}, target_coc={pre.buy_box.target_coc}, "
        f"markets={pre.buy_box.markets}, "
        f"unit_range={pre.buy_box.unit_range}, price_range={pre.buy_box.price_range}"
    )

    # ---- 1) Loader accepts the new tool + internal action ----------------
    reeve = load_agent("reeve")
    assert "update_buy_box" in reeve.tool_names
    assert "update_investor_context" in reeve.internal_actions
    print(f"  loader: reeve has {len(reeve.tool_names)} tools "
          f"({sorted(reeve.tool_names)})")

    # ---- 2) Reeve calls update_buy_box with only unit_range + price_range -
    scripted = [
        _Resp([_Block("tool_use", id="r1", name="update_buy_box", input={
            "unit_range": [4, 16],
            "price_range": [500000, 2000000],
        })]),
        _Resp([_Block("text", text="Buy-box updated: unit range 4–16, price $500k–$2M.")]),
    ]
    llm_mod.set_async_client(_FakeAnthropic(scripted))

    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(reeve, "Set my unit range to 4-16 and price range to $500k-$2M.", ctx)
    assert "update_buy_box" in result.tools_called

    # ---- 3) Mongo holds the new values; the others are untouched ----------
    post = await get_investor(investor.id)
    assert post.buy_box.unit_range == (4, 16), post.buy_box.unit_range
    assert post.buy_box.price_range == (500000.0, 2000000.0), post.buy_box.price_range
    # Untouched fields stayed the same.
    assert post.buy_box.cap_floor == 0.07
    assert post.buy_box.min_dscr == 1.20
    assert post.buy_box.target_coc == 0.08
    assert post.buy_box.markets == ["Westfield, NJ", "Summit, NJ", "Columbus, OH"]
    print(f"  patched: unit_range={post.buy_box.unit_range}, "
          f"price_range={post.buy_box.price_range}")
    print(f"  unchanged: cap_floor={post.buy_box.cap_floor}, "
          f"min_dscr={post.buy_box.min_dscr}, target_coc={post.buy_box.target_coc}, "
          f"markets={post.buy_box.markets}")

    # ---- 4) A second patch on a different field doesn't reset the prior ---
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="r1", name="update_buy_box", input={
            "cap_floor": 0.075,
        })]),
        _Resp([_Block("text", text="Cap floor tightened to 7.5%.")]),
    ]))
    await run_agent(reeve, "Tighten the cap floor to 7.5%.", ctx)
    post2 = await get_investor(investor.id)
    assert post2.buy_box.cap_floor == 0.075
    assert post2.buy_box.unit_range == (4, 16)  # still there
    assert post2.buy_box.price_range == (500000.0, 2000000.0)  # still there
    print(f"  second patch (cap_floor only): cap_floor={post2.buy_box.cap_floor}, "
          f"unit_range still {post2.buy_box.unit_range}")

    # ---- 5) Audit captured act_internal on update_buy_box -----------------
    act_evts = [
        e for e in audit.events
        if e.get("kind") == "act_internal"
        and (e.get("detail") or {}).get("tool") == "update_buy_box"
    ]
    assert len(act_evts) >= 2, act_evts
    print(f"  audit: {len(act_evts)} act_internal events on update_buy_box")

    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
