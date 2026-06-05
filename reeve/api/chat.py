"""POST /api/chat — SSE. investor_id is derived from the bearer token."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..models.message import MessageRole
from ..repos.conversations import create_conversation, get_conversation
from ..repos.investors import get_investor
from ..repos.messages import append_message
from ..runtime import RunContext, load_agent, run_agent
from .auth import require_investor_id


router = APIRouter()


class Inbound(BaseModel):
    message: str
    conversation_id: str | None = None
    agent: str = "reeve"


@router.post("/chat")
async def chat(
    inb: Inbound,
    investor_id: str = Depends(require_investor_id),
):
    investor = await get_investor(investor_id)
    if investor is None:
        from .auth import AuthError
        raise AuthError("investor in token no longer exists")

    if inb.conversation_id:
        conv = await get_conversation(inb.conversation_id)
        if conv is None or conv.investor_id != investor_id:
            raise HTTPException(404, "conversation not found")
    else:
        title = inb.message.strip().splitlines()[0][:80]
        conv = await create_conversation(investor_id, title=title)

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
                    investor_id=investor_id,
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
            except Exception as e:
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
