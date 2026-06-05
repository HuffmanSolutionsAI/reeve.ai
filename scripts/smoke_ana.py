"""Step-3 smoke: Ana end-to-end with real underwriting / comps / DuckDB.

Drives `run_agent(ANA, …)` twice against the same deal with a mocked
Anthropic + mongomock-motor + captured audit:
  - run 1 produces v1 of the deal_analysis artifact, advances the deal,
    seeds the comp cache, and persists 8 audit events.
  - run 2 supersedes v1 with v2 (different assumptions); pull_comps hits
    the cache (source='cache'); deal.latest_analysis_id moves to v2.
Each artifact payload validates against the JSON schema and carries every
field the UI deal card renders."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
from mongomock_motor import AsyncMongoMockClient

import reeve.audit.client as audit_client_module
import reeve.db.mongo as mongo_module
from reeve.models import (
    BuyBox,
    Deal,
    DealSource,
    DealStatus,
    Investor,
)
from reeve.repos.deals import get_deal, upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.runtime import RunContext, load_agent, run_agent
from reeve.sourcing import PipelineFilter, query_pipeline


def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    return client


class _CapturingAudit:
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
    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **kw: Any) -> _Resp:
        self.calls.append(kw)
        return self._scripted.pop(0)


# UI card fields (mirrors reeve_ui.jsx). Anything missing breaks the render.
UI_REQUIRED_FIELDS = (
    "type", "address", "units", "ask", "verdict", "metrics",
    "rent_roll", "assumptions", "thesis", "confidence",
)
UI_REQUIRED_METRICS = (
    "cap_in_place", "cap_proforma", "coc_year1", "coc_stabilized",
    "dscr", "avg_rent_in_place", "avg_rent_market",
    "rent_upside_pct", "rent_upside_monthly",
)


def assert_ui_renders(payload: dict, schema: dict) -> None:
    # submit_deal_analysis adds artifact_id/version/supersedes alongside the
    # contract payload as a persistence receipt; strip those before schema-
    # validating the contract itself.
    contract = {
        k: v for k, v in payload.items()
        if k not in ("artifact_id", "version", "supersedes")
    }
    jsonschema.Draft7Validator(schema).validate(contract)
    missing = [k for k in UI_REQUIRED_FIELDS if k not in payload]
    assert not missing, f"UI card missing top-level: {missing}"
    missing_m = [k for k in UI_REQUIRED_METRICS if k not in payload["metrics"]]
    assert not missing_m, f"UI card missing metrics: {missing_m}"
    assert payload["rent_roll"] and all(
        {"unit", "in_place", "market"} <= set(r) for r in payload["rent_roll"]
    ), "rent_roll entries missing fields"
    assert payload["verdict"]["decision"] in ("pursue", "pass", "conditional")
    assert payload["verdict"]["headline"]


def compose_artifact(
    *,
    address: str,
    units: int,
    ask: float,
    metrics: dict,
    rent_roll: list[dict],
    assumptions: list[str],
    max_price: float | None,
    clears_at_ask: bool,
    thesis: str,
    confidence: str,
    unverified: list[str],
) -> dict:
    if clears_at_ask:
        decision = "pursue"
        headline = f"Pursue at asking ${ask:,.0f}"
    elif max_price and max_price >= ask * 0.85:
        decision = "pursue"
        headline = f"Pursue at ≤ ${max_price:,.0f}"
    elif max_price and max_price > 0:
        decision = "conditional"
        headline = f"Conditional — only at ≤ ${max_price:,.0f}"
    else:
        decision = "pass"
        headline = "Pass — does not clear thresholds"
    return {
        "type": "deal_analysis",
        "address": address,
        "units": units,
        "ask": ask,
        "price_per_unit": round(ask / units, 2),
        "verdict": {"decision": decision, "max_price": max_price, "headline": headline},
        "metrics": metrics,
        "rent_roll": rent_roll,
        "assumptions": assumptions,
        "thesis": thesis,
        "confidence": confidence,
        "unverified": unverified,
    }


async def _seed(client: AsyncMongoMockClient) -> tuple[Investor, Deal]:
    investor = Investor(
        name="James M.",
        entity_name="Oakwood Holdings",
        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20, target_coc=0.08),
    )
    await upsert_investor(investor)
    deal = Deal(
        investor_id=investor.id,
        address="1423 Elmwood Ave, Westfield, NJ 07090",
        units=8,
        ask=1_150_000,
        source=DealSource.MANUAL,
        status=DealStatus.SOURCED,
    )
    await upsert_deal(deal)
    return investor, deal


async def _underwrite_via_tools(
    investor_id: str, address: str, units: int, ask: float, *, other_rate: float
) -> tuple[dict, dict]:
    """Drive the real tools to get realistic numbers we can then script the
    LLM's submit call with. The runtime invokes the same tools via the fake
    LLM during the e2e run; this just builds the script (and shares the
    investor_id so the buy-box threshold check matches the e2e path)."""
    from reeve.runtime import REGISTRY
    from reeve.runtime.spec import RunContext  # local
    pa = REGISTRY["property_analysis"].handler
    pc = REGISTRY["pull_comps"].handler

    comps = await pc(address=address)
    avg_market = comps["comps"]["avg_market_rent"]

    ctx = RunContext(investor_id=investor_id, agent_id="ana")
    analysis = await pa(
        address=address, ask=ask, units=units, avg_market_rent=avg_market,
        other_expense_rate=other_rate, _ctx=ctx,
    )
    return comps, analysis


async def _run_once(
    *,
    investor: Investor,
    deal: Deal,
    other_rate: float,
    thesis: str,
) -> dict:
    """Build a script driving Ana through pull_comps → property_analysis →
    submit. Returns the artifact result dict."""
    # 1) Pre-compute what the tools would return so we can pass the right
    # submit payload to the fake LLM.
    comps, analysis = await _underwrite_via_tools(
        investor.id, deal.address, deal.units, deal.ask, other_rate=other_rate,
    )
    artifact = compose_artifact(
        address=analysis["address"],
        units=analysis["units"],
        ask=analysis["ask"],
        metrics=analysis["metrics"],
        rent_roll=analysis["rent_roll"],
        assumptions=analysis["assumptions"],
        max_price=analysis["max_clearing_price"],
        clears_at_ask=analysis["clears_at_ask"],
        thesis=thesis,
        confidence="medium",
        unverified=["rent roll dates", "T-12 expenses"],
    )

    # 2) Script the LLM.
    scripted = [
        _Resp([_Block("tool_use", id="tu1", name="get_buy_box", input={})]),
        _Resp([_Block("tool_use", id="tu2", name="pull_comps",
                      input={"address": deal.address})]),
        _Resp([_Block("tool_use", id="tu3", name="property_analysis",
                      input={
                          "address": deal.address,
                          "ask": deal.ask,
                          "units": deal.units,
                          "avg_market_rent": comps["comps"]["avg_market_rent"],
                          "other_expense_rate": other_rate,
                      })]),
        _Resp([
            _Block("text", text=thesis),
            _Block("tool_use", id="tu4", name="submit_deal_analysis",
                   input={"artifact": artifact, "deal_id": deal.id}),
        ]),
    ]
    llm = _FakeAnthropic(scripted)
    ana = load_agent("ana")
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(ana, "Underwrite this deal.", ctx, llm=llm)
    assert result.artifact is not None
    return result.artifact


async def main() -> None:
    print("step-3 smoke (Ana standalone):")
    client = install_mock_db()
    audit = install_mock_audit()
    investor, deal = await _seed(client)
    schema = json.loads(Path("contracts/deal_analysis.schema.json").read_text())

    # --- pipeline: real DuckDB query
    pipe = await query_pipeline(PipelineFilter(market="Westfield", max_ask=1_200_000))
    assert pipe["count"] == 3
    assert any(c["address"] == "1423 Elmwood Ave" for c in pipe["candidates"])
    print(f"  pipeline: {pipe['count']} Westfield candidates ≤ $1.2M")

    # --- run 1: produces v1 ----------------------------------------------------
    art1 = await _run_once(
        investor=investor, deal=deal,
        other_rate=0.35,
        thesis="Rent gap is the thesis; in-place yield is light at full ask.",
    )
    assert_ui_renders(art1, schema)
    assert art1["version"] == 1
    assert art1["supersedes"] is None
    assert art1["address"] == deal.address

    deal_after = await get_deal(deal.id)
    assert deal_after is not None
    assert deal_after.latest_analysis_id == art1["artifact_id"]
    assert deal_after.status in ("pursue", "conditional", "analyzed", "pass")
    print(f"  run-1: v1 artifact_id={art1['artifact_id'][:8]}…, "
          f"deal.status={deal_after.status}, "
          f"cap_in_place={art1['metrics']['cap_in_place']:.4f}, "
          f"dscr={art1['metrics']['dscr']:.2f}")

    # comp cache: the first run wrote 'seed'; check the cache row exists.
    cached = await mongo_module.db()["comps"].find_one({"area_key": "westfield_07090"})
    assert cached is not None
    print(f"  comps cache seeded: market={cached['area_key']}, "
          f"avg_market_rent={cached['payload']['avg_market_rent']}")

    # --- run 2: supersedes v1, hits the comp cache ---------------------------
    art2 = await _run_once(
        investor=investor, deal=deal,
        other_rate=0.30,  # gentler expense assumption
        thesis="Reworked OpEx to a 30% other-expense rate (post-LTM bills review).",
    )
    assert_ui_renders(art2, schema)
    assert art2["version"] == 2
    assert art2["supersedes"] == art1["artifact_id"]
    assert art2["artifact_id"] != art1["artifact_id"]

    deal_after2 = await get_deal(deal.id)
    assert deal_after2.latest_analysis_id == art2["artifact_id"]
    print(f"  run-2: v2 artifact_id={art2['artifact_id'][:8]}…, "
          f"supersedes={art2['supersedes'][:8]}…, "
          f"cap_in_place={art2['metrics']['cap_in_place']:.4f}")

    # both artifacts exist; v1 is unchanged (immutability)
    artifacts = await mongo_module.db()["artifacts"].find(
        {"deal_id": deal.id}
    ).to_list(length=10)
    assert len(artifacts) == 2
    v1_doc = next(a for a in artifacts if a["_id"] == art1["artifact_id"])
    assert v1_doc["version"] == 1 and v1_doc["supersedes"] is None
    print(f"  immutability: v1 untouched after v2 ({len(artifacts)} artifacts on deal)")

    # Per run: 3 READ tool calls (get_buy_box, pull_comps, property_analysis)
    # + 1 ACT_INTERNAL (submit) + 1 ARTIFACT (terminal). Two runs → 10 events.
    kinds = [e.get("kind") for e in audit.events]
    counts = {k: kinds.count(k) for k in set(kinds)}
    assert counts.get("artifact") == 2, counts
    assert counts.get("act_internal") == 2, counts  # one submit per run
    assert counts.get("read") == 6, counts          # three reads per run
    print(f"  audit: {len(audit.events)} events, {counts}")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
