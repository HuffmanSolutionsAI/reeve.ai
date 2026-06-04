from .base import BaseDoc


class Conversation(BaseDoc):
    investor_id: str
    title: str | None = None
