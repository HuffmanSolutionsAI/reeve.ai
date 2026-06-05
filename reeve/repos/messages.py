from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.message import DecisionRequest, Handoff, Message, MessageRole


async def _next_seq(conversation_id: str) -> int:
    coll = db()[COLLECTIONS["messages"]]
    last = await coll.find_one(
        {"conversation_id": conversation_id},
        sort=[("seq", -1)],
        projection={"seq": 1},
    )
    return (last["seq"] + 1) if last else 1


async def append_message(
    conversation_id: str,
    *,
    speaker: str,
    role: MessageRole,
    text: str,
    handoffs: list[Handoff] | None = None,
    artifact_ids: list[str] | None = None,
    decision_request: DecisionRequest | None = None,
) -> Message:
    seq = await _next_seq(conversation_id)
    msg = Message(
        conversation_id=conversation_id,
        seq=seq,
        speaker=speaker,
        role=role,
        text=text,
        handoffs=handoffs or [],
        artifact_ids=artifact_ids or [],
        decision_request=decision_request,
    )
    await db()[COLLECTIONS["messages"]].insert_one(msg.model_dump(by_alias=True))
    return msg


async def list_messages(conversation_id: str) -> list[Message]:
    cursor = (
        db()[COLLECTIONS["messages"]]
        .find({"conversation_id": conversation_id})
        .sort([("seq", 1)])
    )
    return [Message.model_validate(doc) async for doc in cursor]
