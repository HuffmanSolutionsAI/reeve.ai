"""Step-4 smoke: drive the FastAPI app end-to-end with mongomock + a mocked
Anthropic. Asserts the SSE event sequence, that conversations/messages
persist, and that the REST endpoints return the expected data."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Force the Mongo audit backend BEFORE config is read elsewhere.
os.environ["AUDIT_BACKEND"] = "mongo"

from mongomock_motor import AsyncMongoMockClient

import reeve.audit as audit_mod
import reeve.db.mongo as mongo_module
from reeve.api import build_app
from reeve.audit import AuditEvent, AuditKind
from reeve.models import BuyBox, Deal, DealSource, DealStatus, Investor
from reeve.repos.deals import upsert_deal
from reeve.repos.investors import upsert_investor


# ---- mocks ----------------------------------------------------------------
def install_mock_db() -> AsyncMongoMockClient:
    client = AsyncMongoMockClient()
    mongo_module._client = client
    return client


class _InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def emit(self, **kw: Any) -> AuditEvent:
        ev = AuditEvent(**kw)
        self.events.append(ev)
        return ev

    def write(self, event: AuditEvent) -> AuditEvent:
        self.events.append(event)
        return event

    def feed(self, investor_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        evs = [e for e in self.events if e.investor_id == investor_id]
        return [e.model_dump() for e in evs[-limit:][::-1]]

    def by_entity(self, entity_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        evs = [e for e in self.events if e.entity_id == entity_id]
        return [e.model_dump() for e in evs[-limit:][::-1]]


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
    """A scripted LLM that returns canned responses in order. dispatch turns
    into Ana's sub-run, so we also script Ana's turns."""

    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.messages = self
        self.calls: list[dict] = []

    async def create(self, **kw: Any) -> _Resp:
        self.calls.append(kw)
        return self._scripted.pop(0)


def install_mock_llm(scripted: list[_Resp]) -> _FakeAnthropic:
    import reeve.runtime.runner as runner_module
    fake = _FakeAnthropic(scripted)
    runner_module._client_singleton = fake
    return fake


def sample_payload(ask: float = 1_150_000) -> dict:
    return {
        "type": "deal_analysis",
        "address": "1423 Elmwood Ave, Westfield, NJ 07090",
        "units": 8,
        "ask": ask,
        "price_per_unit": ask / 8,
        "verdict": {"decision": "pursue", "max_price": 1_060_000, "headline": "Pursue at ≤ $1.06M"},
        "metrics": {
            "cap_in_place": 0.054, "cap_proforma": 0.069, "coc_year1": 0.041,
            "coc_stabilized": 0.087, "dscr": 1.24,
            "avg_rent_in_place": 1233, "avg_rent_market": 1466,
            "rent_upside_pct": 0.19, "rent_upside_monthly": 1864,
        },
        "rent_roll": [{"unit": f"{(i // 2) + 1}{'AB'[i % 2]}",
                       "in_place": 1233, "market": 1466} for i in range(8)],
        "assumptions": ["Vacancy 5%", "Mgmt 8%", "Other OpEx 35% of EGI",
                        "CapEx $300/unit/yr", "6.75% · 25yr · 70% LTV"],
        "thesis": "Eight units running 19% under market — upside is real.",
        "confidence": "medium",
        "unverified": ["rent roll dates"],
    }


async def _seed(investor_id_out: list[str]) -> str:
    investor = Investor(
        name="James M.", entity_name="Oakwood Holdings",
        buy_box=BuyBox(cap_floor=0.07, min_dscr=1.20, target_coc=0.08),
    )
    await upsert_investor(investor)
    deal = Deal(
        investor_id=investor.id,
        address="1423 Elmwood Ave, Westfield, NJ 07090",
        units=8, ask=1_150_000, source=DealSource.MANUAL,
        status=DealStatus.SOURCED,
    )
    await upsert_deal(deal)
    investor_id_out.append(investor.id)
    return deal.id


# ---- SSE parsing helper ---------------------------------------------------
def parse_sse(body: str) -> list[tuple[str, dict]]:
    # SSE events end with a blank line. The spec uses CRLF; normalize first.
    events: list[tuple[str, dict]] = []
    for chunk in body.replace("\r\n", "\n").split("\n\n"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        event = "message"
        data = ""
        for line in chunk.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        try:
            payload = json.loads(data) if data else {}
        except json.JSONDecodeError:
            payload = {"raw": data}
        events.append((event, payload))
    return events


# ---- tests ----------------------------------------------------------------
async def main() -> None:
    print("step-4 smoke (SSE + REST):")
    install_mock_db()
    audit = install_mock_audit()
    investor_holder: list[str] = []
    deal_id = await _seed(investor_holder)
    investor_id = investor_holder[0]

    # Script: Reeve dispatches to Ana → Ana runs 4 tools → Ana submits →
    # Reeve composes a closing text. 6 total LLM turns.
    scripted = [
        # Reeve turn 1: dispatch to Ana
        _Resp([_Block("tool_use", id="r1", name="dispatch",
                      input={"agent_id": "ana", "task": "Underwrite 1423 Elmwood at $1.15M."})]),
        # Ana turn 1: get_buy_box
        _Resp([_Block("tool_use", id="a1", name="get_buy_box", input={})]),
        # Ana turn 2: pull_comps
        _Resp([_Block("tool_use", id="a2", name="pull_comps",
                      input={"address": "1423 Elmwood Ave, Westfield, NJ 07090"})]),
        # Ana turn 3: property_analysis
        _Resp([_Block("tool_use", id="a3", name="property_analysis",
                      input={"address": "1423 Elmwood Ave, Westfield, NJ 07090",
                             "ask": 1_150_000, "units": 8, "avg_market_rent": 1466})]),
        # Ana turn 4: submit
        _Resp([
            _Block("text", text="Pursue at ≤ $1.06M."),
            _Block("tool_use", id="a4", name="submit_deal_analysis",
                   input={"artifact": sample_payload(), "deal_id": deal_id}),
        ]),
        # Reeve turn 2: final text after dispatch returns
        _Resp([_Block("text", text="Net: good building at the wrong price. Anchor at $1.06M.")]),
    ]
    install_mock_llm(scripted)

    app = build_app()
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        # --- POST /api/chat (SSE) -------------------------------------------
        with client.stream(
            "POST", "/api/chat",
            json={"investor_id": investor_id, "message": "Look at 1423 Elmwood, 8u, $1.15M."},
        ) as resp:
            assert resp.status_code == 200, resp.read().decode()
            body = b"".join(resp.iter_bytes()).decode()
        events = parse_sse(body)
        types = [e[0] for e in events]
        print(f"  sse types: {types}")
        # Required event types in expected order
        assert "conversation" in types
        assert types.index("conversation") < types.index("done")
        assert "routing" in types
        assert "handoff" in types
        assert "artifact" in types
        assert "message" in types
        assert types[-1] == "done"
        # Routing happens for both Reeve and Ana
        assert types.count("routing") >= 2
        # An artifact event carries the full payload
        artifact_event = next(e[1] for e in events if e[0] == "artifact")
        assert artifact_event["type"] == "deal_analysis"
        assert artifact_event["payload"]["address"] == "1423 Elmwood Ave, Westfield, NJ 07090"
        assert artifact_event["artifact_id"]

        conv_event = next(e[1] for e in events if e[0] == "conversation")
        conv_id = conv_event["id"]

        # --- GET /api/conversations/:id/messages ----------------------------
        r = client.get(f"/api/conversations/{conv_id}/messages")
        assert r.status_code == 200
        data = r.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["speaker"] == "investor"
        assert data["messages"][1]["speaker"] == "reeve"
        assert data["messages"][1]["text"]
        assert data["messages"][1]["artifact_ids"]
        print(f"  /messages: {len(data['messages'])} messages persisted, "
              f"reeve text={data['messages'][1]['text'][:48]!r}…")

        # --- GET /api/pipeline ----------------------------------------------
        r = client.get(f"/api/pipeline?investor_id={investor_id}")
        assert r.status_code == 200
        pipe = r.json()
        # Status should have advanced to 'pursue' from the artifact submit
        assert pipe["counts"].get("pursue", 0) >= 1
        print(f"  /pipeline: counts={dict(pipe['counts'])}")

        # --- GET /api/portfolio ---------------------------------------------
        r = client.get(f"/api/portfolio?investor_id={investor_id}")
        assert r.status_code == 200
        portf = r.json()
        assert "portfolios" in portf
        print(f"  /portfolio: {portf['totals']} (empty until seed_dev runs against real Mongo)")

        # --- GET /api/activity ----------------------------------------------
        r = client.get(f"/api/activity?investor_id={investor_id}")
        assert r.status_code == 200
        act = r.json()
        assert len(act["events"]) >= 5
        kinds = {e["kind"] for e in act["events"]}
        assert "artifact" in kinds and "act_internal" in kinds and "read" in kinds
        print(f"  /activity: {len(act['events'])} events, kinds={sorted(kinds)}")

        # --- GET /api/artifacts/:id -----------------------------------------
        r = client.get(f"/api/artifacts/{artifact_event['artifact_id']}")
        assert r.status_code == 200
        art = r.json()
        assert art["type"] == "deal_analysis"
        assert art["payload"]["address"] == "1423 Elmwood Ave, Westfield, NJ 07090"
        print(f"  /artifacts/:id: v{art['version']}, deal_id={art['deal_id'][:8]}…")

    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
