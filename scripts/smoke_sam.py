"""Step-7 smoke: Sam sources, dedupes, and seeds Ana's pipeline.

Drives Sam end-to-end against the real DuckDB pipeline + mongomock.
Verifies:
  - Sam reads the buy-box, queries the pipeline, lists existing deals.
  - submit_sourcing_summary persists new Deal rows with source=sam,
    status=sourced — and stamps deal_ids on the artifact's candidates.
  - A candidate that matches an existing pipeline row is marked
    duplicate=true and NOT persisted twice (the submit-time dedupe).
  - The artifact validates against sourcing_summary.schema.json.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("AUDIT_BACKEND", "mongo")
os.environ.setdefault("PROPOSALS_BACKEND", "mongo")

import jsonschema
from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
import reeve.proposals as proposals_mod
from reeve.models import (
    BuyBox,
    Deal,
    DealSource,
    DealStatus,
    Investor,
    Portfolio,
)
from reeve.repos.deals import upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.runtime import RunContext, load_agent, run_agent
from reeve.sourcing import PipelineFilter, query_pipeline


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

    def write(self, event: Any) -> Any:
        self.events.append(event.model_dump() if hasattr(event, "model_dump") else event)
        return event

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


async def _seed() -> tuple[Investor, Deal]:
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(
            cap_floor=0.07, min_dscr=1.20, target_coc=0.08,
            markets=["Westfield, NJ"],
            unit_range=(4, 12), price_range=(400_000, 2_000_000),
        ),
    )
    await upsert_investor(investor)
    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    await mongo_module.db()["portfolios"].insert_one(portfolio.model_dump(by_alias=True))
    # An existing deal Sam should detect as a duplicate.
    existing = Deal(
        investor_id=investor.id,
        address="412 Lincoln St",
        units=4, ask=720_000, source=DealSource.MANUAL,
        status=DealStatus.SOURCED,
    )
    await upsert_deal(existing)
    return investor, existing


async def main() -> None:
    print("step-7 smoke (Sam — sourcing):")
    install_mock_db()
    audit = install_mock_audit()
    investor, existing = await _seed()

    # ---- precompute what Sam's tools would return --------------------------
    pipe = await query_pipeline(PipelineFilter(market="Westfield", max_ask=1_200_000))
    assert pipe["count"] >= 2, pipe
    print(f"  pipeline scan: {pipe['count']} Westfield candidates ≤ $1.2M")

    today = datetime.now(timezone.utc).date().isoformat()
    summary_payload = {
        "type": "sourcing_summary",
        "as_of": today,
        "filters": {"market": "Westfield", "max_ask": 1_200_000},
        "scanned": pipe["count"],
        "duplicates": 0,  # submit will recompute
        "surfaced": 0,    # submit will recompute
        "candidates": [
            {
                "address": c["address"], "city": c["city"], "state": c["state"],
                "zip": c["zip"], "units": c["units"], "ask": c["ask"],
                "year_built": c["year_built"],
                "distress_signal": c["distress_signal"],
                "fit_score": min(
                    1.0,
                    0.30 * (c["city"] == "Westfield")
                    + 0.20 * (4 <= c["units"] <= 12)
                    + 0.30 * (400_000 <= c["ask"] <= 2_000_000)
                    + 0.20 * (c["ask"] / max(c["units"], 1) < 200_000)
                ),
                "rationale": (
                    f"{c['units']}u in {c['city']}, ${c['ask']:,} "
                    f"(${round(c['ask'] / c['units']):,}/unit); "
                    f"signal: {c['distress_signal']}."
                ),
                # Sam classifies the profile from the distress signal —
                # routes Ana's underwriter downstream.
                "profile": (
                    "distressed" if c["distress_signal"] in ("tax lien", "high vacancy")
                    else "value_add" if c["distress_signal"] == "deferred maintenance"
                    else "stabilized"
                ),
            }
            for c in pipe["candidates"]
        ],
        "thesis": (
            f"Westfield pipeline yielded {pipe['count']} candidates fitting "
            f"the buy-box; recommend Ana on the highest fit_score."
        ),
        "confidence": "high",
        "unverified": [],
    }

    # ---- script Sam's run --------------------------------------------------
    scripted = [
        _Resp([_Block("tool_use", id="s1", name="get_buy_box", input={})]),
        _Resp([_Block("tool_use", id="s2", name="list_existing_deals", input={})]),
        _Resp([_Block("tool_use", id="s3", name="query_sourcing_pipeline",
                      input={"market": "Westfield", "max_ask": 1_200_000})]),
        _Resp([
            _Block("text", text="Three Westfield candidates fit the buy-box."),
            _Block("tool_use", id="s4", name="submit_sourcing_summary",
                   input={"artifact": summary_payload}),
        ]),
    ]
    import reeve.llm as llm_mod
    llm_mod.set_async_client(_FakeAnthropic(scripted))

    sam = load_agent("sam")
    assert sam.id == "sam" and sam.terminal_tool == "submit_sourcing_summary"
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    result = await run_agent(sam, "Find me new Westfield deals.", ctx)

    assert result.artifact is not None
    assert result.artifact["type"] == "sourcing_summary"
    schema = json.loads(Path("contracts/sourcing_summary.schema.json").read_text())
    contract_only = {k: v for k, v in result.artifact.items()
                     if k not in ("artifact_id", "version", "supersedes")}
    jsonschema.Draft7Validator(schema).validate(contract_only)

    cands = result.artifact["candidates"]
    surfaced = [c for c in cands if not c.get("duplicate")]
    duplicates = [c for c in cands if c.get("duplicate")]

    # 412 Lincoln St was seeded as MANUAL → must come back as a duplicate.
    dup_addrs = {c["address"] for c in duplicates}
    assert existing.address in dup_addrs, dup_addrs
    print(f"  surfaced={len(surfaced)}, duplicates={len(duplicates)} (incl. {existing.address!r})")

    # Each surfaced candidate produced a new Deal with source=sam, status=sourced.
    for c in surfaced:
        assert c.get("deal_id"), f"surfaced candidate missing deal_id: {c}"
    sam_deals = []
    async for d in mongo_module.db()["deals"].find({"source": "sam"}):
        sam_deals.append(d)
    assert len(sam_deals) == len(surfaced), (len(sam_deals), len(surfaced))
    addr_to_status = {d["address"]: d["status"] for d in sam_deals}
    assert all(s == "sourced" for s in addr_to_status.values()), addr_to_status
    print(f"  persisted {len(sam_deals)} Deal rows with source=sam, status=sourced")

    # Profile classification landed on the Deal rows (routes Ana downstream).
    surfaced_by_addr = {c["address"]: c for c in surfaced}
    for d in sam_deals:
        expected_profile = surfaced_by_addr[d["address"]].get("profile") or "stabilized"
        assert d.get("profile") == expected_profile, (d["address"], d.get("profile"), expected_profile)
    profiles = {d["address"]: d["profile"] for d in sam_deals}
    assert set(profiles.values()) & {"value_add", "distressed"}, profiles
    print(f"  deal profiles routed: { {a.split(',')[0]: p for a, p in profiles.items()} }")

    # Idempotency: a second Sam run on the same candidates should surface 0.
    llm_mod.set_async_client(_FakeAnthropic([
        _Resp([_Block("tool_use", id="s1", name="get_buy_box", input={})]),
        _Resp([_Block("tool_use", id="s2", name="list_existing_deals", input={})]),
        _Resp([_Block("tool_use", id="s3", name="query_sourcing_pipeline",
                      input={"market": "Westfield", "max_ask": 1_200_000})]),
        _Resp([
            _Block("text", text="All duplicates this pass."),
            _Block("tool_use", id="s4", name="submit_sourcing_summary",
                   input={"artifact": summary_payload}),
        ]),
    ]))
    result2 = await run_agent(sam, "Find me new Westfield deals.", ctx)
    surfaced2 = [c for c in result2.artifact["candidates"] if not c.get("duplicate")]
    assert surfaced2 == [], f"re-run surfaced {len(surfaced2)} duplicates"
    print(f"  idempotency: 2nd run surfaced 0 (all marked duplicate)")

    # Audit captured the run.
    kinds = [e.get("kind") for e in audit.events]
    assert "act_internal" in kinds and "artifact" in kinds
    print(f"  audit: {len(audit.events)} events, kinds={sorted(set(kinds))}")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
