"""Reeve runtime entrypoint.

The previous scaffold of this file (in-memory stores, sync LLM loop) has been
fleshed out into the `reeve` package:
  - `reeve.runtime`         — Tier, AgentSpec, run_agent, scope enforcement
  - `reeve.runtime.tools.*` — registered Tool handlers
  - `reeve.repos.*`         — Mongo-backed persistence (deals, artifacts, runs)
  - `reeve.audit`           — append-only DynamoDB audit log

This file stays as the FastAPI entry. SSE streaming is wired in §8 step 4.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from reeve.db.mongo import ensure_indexes
from reeve.runtime import (
    REGISTRY,
    RunContext,
    list_agents,
    load_agent,
    run_agent,
)


app = FastAPI(title="Reeve", version="0.1.0")


@app.on_event("startup")
async def _on_startup() -> None:
    await ensure_indexes()


class Inbound(BaseModel):
    message: str
    investor_id: str
    conversation_id: str | None = None


@app.post("/chat")
async def chat(inb: Inbound) -> dict:
    spec = load_agent("reeve")
    ctx = RunContext(
        investor_id=inb.investor_id,
        conversation_id=inb.conversation_id,
    )
    result = await run_agent(spec, inb.message, ctx)
    return {
        "speaker": "Reeve",
        "text": result.text,
        "artifacts": [result.artifact] if result.artifact else [],
        "proposal_ids": result.proposal_ids,
        "status": result.status,
    }


@app.get("/agents")
def agents() -> dict:
    return {
        "available": list_agents(),
        "tools": sorted(REGISTRY.keys()),
    }
