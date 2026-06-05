"""LLM provider + alias-resolution smoke.

Verifies that:
  - Default provider (`anthropic`) doesn't rewrite model ids.
  - `LLM_PROVIDER=bedrock` rewrites known friendly names to the
    built-in Bedrock defaults.
  - BEDROCK_MODEL_ALIASES (JSON env) overrides the built-ins.
  - The runner picks up a mock client installed via
    `reeve.llm.set_async_client` and forwards `resolve_model(spec.model)`
    when invoking the LLM."""
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
from reeve.config import settings
from reeve.models import BuyBox, Investor
from reeve.repos.investors import upsert_investor
from reeve.runtime import RunContext, load_agent, run_agent


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
    id: str | None = None
    name: str | None = None
    input: dict | None = None


@dataclass
class _Resp:
    content: list[_Block]


class _CaptureClient:
    """Records the `model` kwarg of every messages.create call."""

    def __init__(self, scripted: list[_Resp]) -> None:
        self._scripted = list(scripted)
        self.messages = self
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kw: Any) -> _Resp:
        self.calls.append(kw)
        return self._scripted.pop(0)


async def main() -> None:
    print("smoke_llm_provider:")

    # ---- 1) Direct API mode: resolve_model is a no-op --------------------
    settings.llm_provider = "anthropic"
    settings.bedrock_model_aliases = ""
    assert llm_mod.resolve_model("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert llm_mod.resolve_model("some-random-thing") == "some-random-thing"
    print("  anthropic mode: resolve_model is identity")

    # ---- 2) Bedrock mode: built-in defaults kick in ----------------------
    settings.llm_provider = "bedrock"
    settings.bedrock_model_aliases = ""
    # Reset the warn-once cache so re-runs of the smoke don't lose log output.
    llm_mod.client._warned_unmapped.clear()
    haiku = llm_mod.resolve_model("claude-haiku-4-5-20251001")
    assert haiku.startswith("us.anthropic.claude-haiku-4-5-"), haiku
    sonnet = llm_mod.resolve_model("claude-sonnet-4-6")
    assert sonnet.startswith("us.anthropic.claude-sonnet-4-6-"), sonnet
    opus = llm_mod.resolve_model("claude-opus-4-8")
    assert opus.startswith("us.anthropic.claude-opus-4-8-"), opus
    # Unknown model → pass through + log warning (first time only).
    unknown = llm_mod.resolve_model("not-a-real-model")
    assert unknown == "not-a-real-model"
    print(f"  bedrock defaults: haiku→{haiku.split('.')[2][:24]}…, sonnet→{sonnet.split('.')[2][:24]}…")

    # ---- 3) BEDROCK_MODEL_ALIASES override ------------------------------
    settings.bedrock_model_aliases = '{"claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6-CUSTOM-v1:0"}'
    custom = llm_mod.resolve_model("claude-sonnet-4-6")
    assert custom == "us.anthropic.claude-sonnet-4-6-CUSTOM-v1:0", custom
    # Other defaults still apply.
    assert llm_mod.resolve_model("claude-haiku-4-5-20251001") == haiku
    print(f"  env override: claude-sonnet-4-6 → {custom}")

    # ---- 4) Runner forwards resolve_model(spec.model) -------------------
    install_mock_db()
    audit_mod.set_default(_NullAudit())
    investor = Investor(name="James M.", buy_box=BuyBox(cap_floor=0.07))
    await upsert_investor(investor)

    capture = _CaptureClient([_Resp([_Block("text", text="ok")])])
    llm_mod.set_async_client(capture)

    ana = load_agent("ana")
    assert ana.model == "claude-sonnet-4-6"
    ctx = RunContext(investor_id=investor.id, conversation_id="c1")
    await run_agent(ana, "Hi.", ctx)

    assert capture.calls, "runner did not call the client"
    model_used = capture.calls[0]["model"]
    expected = llm_mod.resolve_model(ana.model)
    assert model_used == expected, (model_used, expected)
    print(f"  run_agent: spec.model={ana.model!r} → forwarded to client as {model_used!r}")

    # Cleanup
    settings.llm_provider = "anthropic"
    settings.bedrock_model_aliases = ""
    llm_mod.set_async_client(None)
    print("ok.")


if __name__ == "__main__":
    asyncio.run(main())
