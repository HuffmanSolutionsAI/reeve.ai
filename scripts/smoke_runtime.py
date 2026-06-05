"""Step-2 smoke check: loader, scope vocabulary, scope enforcement, runtime
end-to-end with mocked LLM + mongomock-motor + an in-memory audit, and the
gated-tool intercept that produces a Proposal without executing the handler.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mongomock_motor import AsyncMongoMockClient

import reeve.audit.client as audit_client_module
import reeve.db.mongo as mongo_module
from reeve.models import BuyBox, Deal, DealSource, DealStatus, Investor
from reeve.repos.deals import upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.repos.proposals import PROPOSALS_COLLECTION
from reeve.runtime import (
    REGISTRY,
    KNOWN_GATED_ACTIONS,
    KNOWN_INTERNAL_ACTIONS,
    KNOWN_READ_SCOPES,
    RunContext,
    SpecError,
    check_scope,
    load_agent,
    run_agent,
)


# ---- helpers ---------------------------------------------------------------
def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client  # cached singleton
    return client


class _CapturingAudit:
    """Records every emit; no AWS calls."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, **kw: Any) -> None:
        self.events.append({k: (v.value if hasattr(v, "value") else v) for k, v in kw.items()})

    def write(self, ev: Any) -> Any:
        self.events.append({"raw": ev})
        return ev


def install_mock_audit() -> _CapturingAudit:
    sink = _CapturingAudit()
    audit_client_module._default = sink  # type: ignore[assignment]
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
    """Tiny stand-in for AsyncAnthropic.messages.create — returns canned
    responses in order, one per turn."""

    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **kw: Any) -> _Resp:
        self.calls.append(kw)
        return self._scripted.pop(0)


def sample_payload(ask: float = 1_150_000) -> dict:
    return {
        "type": "deal_analysis",
        "address": "1423 Elmwood Ave",
        "units": 8,
        "ask": ask,
        "price_per_unit": ask / 8,
        "verdict": {"decision": "pursue", "max_price": 1_060_000, "headline": "Pursue at ≤ $1.06M"},
        "metrics": {
            "cap_in_place": 0.054, "cap_proforma": 0.069,
            "coc_year1": 0.041, "coc_stabilized": 0.087,
            "dscr": 1.24,
            "avg_rent_in_place": 1233, "avg_rent_market": 1466,
            "rent_upside_pct": 0.19, "rent_upside_monthly": 1866,
        },
        "rent_roll": [{"unit": "1A", "in_place": 1150, "market": 1450}],
        "assumptions": ["Vacancy 5%", "Mgmt 8%"],
        "thesis": "Rent gap drives the upside.",
        "confidence": "medium",
        "unverified": ["rent roll dates"],
    }


# ---- tests -----------------------------------------------------------------
def test_loader() -> None:
    ana = load_agent("ana")
    assert ana.id == "ana"
    assert ana.terminal_tool == "submit_deal_analysis"
    assert ana.output_contract == "deal_analysis"
    assert "get_buy_box" in ana.tool_names
    assert "write_artifact" in ana.internal_actions
    assert ana.gated_actions == []
    assert "Reeve — house rules" in ana.system_prompt
    assert "Ana — Underwriting" in ana.system_prompt

    reeve = load_agent("reeve")
    # Reeve picks up new tools over time (update_buy_box etc.); just verify
    # dispatch is in there — that's what the loader exercise needs.
    assert "dispatch" in reeve.tool_names
    print(f"  loader: ana={len(ana.tool_names)} tools, reeve={len(reeve.tool_names)}")


def test_scope_vocab_covers_every_declared_label() -> None:
    for agent_id in ("reeve", "ana"):
        spec = load_agent(agent_id)
        assert set(spec.read_scope).issubset(KNOWN_READ_SCOPES), agent_id
        assert set(spec.internal_actions).issubset(KNOWN_INTERNAL_ACTIONS), agent_id
        assert set(spec.gated_actions).issubset(KNOWN_GATED_ACTIONS), agent_id
    print("  vocab: all declared scopes are known")


def test_loader_rejects_unknown_tool() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        # copy real house.md so the loader can compose
        shutil.copy(Path("agents/house.md"), tmp / "house.md")
        (tmp / "bad.md").write_text(
            "---\nid: bad\nname: Bad\ndesk: Asset Mgmt\n"
            "tools: [no_such_tool]\nread_scope: []\n"
            "internal_actions: []\ngated_actions: []\n---\nbody.\n"
        )
        try:
            load_agent("bad", agents_dir=tmp)
        except SpecError as e:
            assert "unknown tool" in str(e).lower()
            print(f"  loader-neg (unknown tool): {e}")
            return
        raise AssertionError("expected SpecError for unknown tool")
    finally:
        shutil.rmtree(tmp)


def test_loader_rejects_unscoped_gated_action() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        shutil.copy(Path("agents/house.md"), tmp / "house.md")
        # send_loi is gated and writes 'send_loi'; bad agent omits it.
        (tmp / "bad.md").write_text(
            "---\nid: bad\nname: Bad\ndesk: Acquisition\n"
            "tools: [send_loi]\nread_scope: []\n"
            "internal_actions: []\ngated_actions: []\n---\nbody.\n"
        )
        try:
            load_agent("bad", agents_dir=tmp)
        except SpecError as e:
            assert "send_loi" in str(e)
            print(f"  loader-neg (missing gated_action): {e}")
            return
        raise AssertionError("expected SpecError for missing gated_action")
    finally:
        shutil.rmtree(tmp)


def test_check_scope() -> None:
    ana = load_agent("ana")
    assert check_scope(ana, REGISTRY["submit_deal_analysis"]) is None
    violation = check_scope(ana, REGISTRY["send_loi"])
    assert violation and "gated action" in violation
    print(f"  check_scope: blocks send_loi for Ana ({violation})")


async def _e2e_ana_run() -> None:
    install_mock_db()
    audit = install_mock_audit()

    investor = Investor(name="James", buy_box=BuyBox(cap_floor=0.07, min_dscr=1.2, target_coc=0.08))
    await upsert_investor(investor)
    deal = Deal(investor_id=investor.id, address="1423 Elmwood Ave",
                ask=1_150_000, units=8, source=DealSource.MANUAL,
                status=DealStatus.SOURCED)
    await upsert_deal(deal)

    scripted = [
        _Resp([_Block("tool_use", id="tu1", name="get_buy_box", input={})]),
        _Resp([_Block("tool_use", id="tu2", name="pull_comps",
                      input={"address": "1423 Elmwood Ave"})]),
        _Resp([_Block("tool_use", id="tu3", name="property_analysis",
                      input={"address": "1423 Elmwood Ave", "ask": 1_150_000,
                             "units": 8, "avg_market_rent": 1466})]),
        _Resp([
            _Block("text", text="Pursue at ≤ $1.06M."),
            _Block("tool_use", id="tu4", name="submit_deal_analysis",
                   input={"artifact": sample_payload(), "deal_id": deal.id}),
        ]),
    ]
    llm = _FakeAnthropic(scripted)

    ana = load_agent("ana")
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(ana, "Underwrite 1423 Elmwood at $1.15M", ctx, llm=llm)

    assert result.artifact is not None, "no artifact emitted"
    assert result.artifact["type"] == "deal_analysis"
    assert "artifact_id" in result.artifact
    assert result.status == "ok"
    assert set(result.tools_called) == {
        "get_buy_box", "property_analysis", "pull_comps", "submit_deal_analysis"
    }

    # the deal advanced
    deal_doc = await mongo_module.db()["deals"].find_one({"_id": deal.id})
    assert deal_doc["status"] == "pursue"
    assert deal_doc["latest_analysis_id"] == result.artifact["artifact_id"]

    # the artifact is persisted with version=1 and the right links
    art = await mongo_module.db()["artifacts"].find_one({"_id": result.artifact["artifact_id"]})
    assert art["version"] == 1 and art["produced_by"] == "ana" and art["deal_id"] == deal.id

    kinds = [e.get("kind") for e in audit.events]
    assert "read" in kinds and "act_internal" in kinds and "artifact" in kinds
    print(f"  e2e: tools={result.tools_called}, artifact_id={result.artifact['artifact_id'][:8]}…, "
          f"audit_events={len(audit.events)}")


async def _e2e_gated_intercept() -> None:
    """Build an ad-hoc agent that has send_loi; verify the runtime emits a
    proposal and the handler is NOT called."""
    install_mock_db()
    audit = install_mock_audit()
    investor = Investor(name="James", buy_box=BuyBox())
    await upsert_investor(investor)

    sentinel: list[str] = []

    # monkeypatch send_loi to detect any direct execution
    original = REGISTRY["send_loi"].handler

    async def tripwire(**kw: Any) -> dict:
        sentinel.append("called")
        return {"sent": True}

    REGISTRY["send_loi"].handler = tripwire

    try:
        tmp = Path(tempfile.mkdtemp())
        shutil.copy(Path("agents/house.md"), tmp / "house.md")
        (tmp / "cole.md").write_text(
            "---\nid: cole\nname: Cole\ndesk: Acquisition\n"
            "model: claude-sonnet-4-6\ntools: [send_loi]\n"
            "read_scope: []\ninternal_actions: []\n"
            "gated_actions: [send_loi]\n---\nbody.\n"
        )
        cole = load_agent("cole", agents_dir=tmp)

        scripted = [
            _Resp([_Block("tool_use", id="tu1", name="send_loi",
                          input={"address": "1423 Elmwood Ave", "price": 1_060_000})]),
            _Resp([_Block("text", text="Proposal queued.")]),
        ]
        llm = _FakeAnthropic(scripted)

        ctx = RunContext(investor_id=investor.id)
        result = await run_agent(cole, "Send LOI at $1.06M", ctx, llm=llm)

        assert sentinel == [], "send_loi handler was executed — gate failed!"
        assert result.artifact is None
        assert len(result.proposal_ids) == 1
        assert result.status == "gated"

        # proposal persisted as pending
        p = await mongo_module.db()[PROPOSALS_COLLECTION].find_one(
            {"_id": result.proposal_ids[0]}
        )
        assert p["status"] == "pending"
        assert p["action"] == "send_loi"
        assert p["payload"]["price"] == 1_060_000

        kinds = [e.get("kind") for e in audit.events]
        assert "proposed" in kinds
        shutil.rmtree(tmp)
        print(f"  gated-intercept: proposal {result.proposal_ids[0][:8]}… queued, handler not called")
    finally:
        REGISTRY["send_loi"].handler = original


def main() -> None:
    print("step-2 smoke:")
    test_loader()
    test_scope_vocab_covers_every_declared_label()
    test_loader_rejects_unknown_tool()
    test_loader_rejects_unscoped_gated_action()
    test_check_scope()
    asyncio.run(_e2e_ana_run())
    asyncio.run(_e2e_gated_intercept())
    print("ok.")


if __name__ == "__main__":
    main()
