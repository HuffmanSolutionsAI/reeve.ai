"""POST /api/chat — SSE.

Event sequence (per inbound message):
  conversation         — the conversation id (use this to hydrate later)
  routing              — Reeve received the prompt
  handoff              — Reeve dispatched to a specialist
  routing              — the specialist received the task
  tool                 — a tool call landed (one per call; working indicator)
  artifact             — terminal artifact emitted (full payload inline)
  message              — assistant final text
  proposal             — a gated action was queued for sign-off
  done                 — terminal sentinel; close the stream
  error                — runtime failure; stream will close after this
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..models.message import MessageRole
from ..repos.conversations import create_conversation, get_conversation
from ..repos.investors import get_investor
from ..repos.messages import append_message
from ..runtime import RunContext, load_agent, run_agent


router = APIRouter()


class Inbound(BaseModel):
    message: str
    investor_id: str
    conversation_id: str | None = None
    agent: str = "reeve"


@router.post("/chat")
async def chat(inb: Inbound):
    investor = await get_investor(inb.investor_id)
    if investor is None:
        raise HTTPException(404, f"investor {inb.investor_id!r} not found")

    if inb.conversation_id:
        conv = await get_conversation(inb.conversation_id)
        if conv is None:
            raise HTTPException(404, "conversation not found")
        if conv.investor_id != inb.investor_id:
            raise HTTPException(403, "conversation belongs to a different investor")
    else:
        title = inb.message.strip().splitlines()[0][:80]
        conv = await create_conversation(inb.investor_id, title=title)

    user_msg = await append_message(
        conv.id,
        speaker="investor",
        role=MessageRole.USER,
        text=inb.message,
    )

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        artifact_ids: list[str] = []

        async def sink(event: dict[str, Any]) -> None:
            if event.get("event") == "artifact" and event.get("artifact_id"):
                artifact_ids.append(event["artifact_id"])
            await queue.put(event)

        async def runner_task() -> None:
            try:
                await queue.put({
                    "event": "conversation",
                    "id": conv.id,
                    "title": conv.title,
                    "user_seq": user_msg.seq,
                })
                spec = load_agent(inb.agent)
                ctx = RunContext(
                    investor_id=inb.investor_id,
                    conversation_id=conv.id,
                    event_sink=sink,
                )
                result = await run_agent(spec, inb.message, ctx)
                await append_message(
                    conv.id,
                    speaker=spec.id,
                    role=MessageRole.ASSISTANT,
                    text=result.text or "",
                    artifact_ids=list(dict.fromkeys(artifact_ids)),
                )
            except Exception as e:  # surface to the client; close the stream
                await queue.put({"event": "error", "message": str(e)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner_task())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    yield {"event": "done", "data": "{}"}
                    return
                event_type = event.pop("event")
                yield {"event": event_type, "data": json.dumps(event, default=str)}
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(event_stream())
