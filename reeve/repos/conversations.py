from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.conversation import Conversation


async def get_conversation(conversation_id: str) -> Conversation | None:
    doc = await db()[COLLECTIONS["conversations"]].find_one({"_id": conversation_id})
    return Conversation.model_validate(doc) if doc else None


async def list_conversations(investor_id: str, *, limit: int = 25) -> list[Conversation]:
    cursor = (
        db()[COLLECTIONS["conversations"]]
        .find({"investor_id": investor_id})
        .sort([("created_at", -1)])
        .limit(limit)
    )
    return [Conversation.model_validate(doc) async for doc in cursor]


async def create_conversation(
    investor_id: str, *, title: str | None = None
) -> Conversation:
    conv = Conversation(investor_id=investor_id, title=title)
    await db()[COLLECTIONS["conversations"]].insert_one(conv.model_dump(by_alias=True))
    return conv
