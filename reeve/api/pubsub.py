"""In-process pub/sub keyed by investor_id.

Each subscriber gets its own bounded asyncio queue; publishes fan out to
every queue for the investor. Used to fan audit events out to the
activity-stream WebSocket without coupling the audit clients to the
transport.

Bounded queues + put_nowait means a slow consumer just drops events
(its WebSocket will catch up via the REST `/api/activity` endpoint
when it reconnects). The audit itself is the source of truth — this
is best-effort delivery for the live feed only."""
from __future__ import annotations

import asyncio
from collections import defaultdict


class PubSub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, investor_id: str, *, maxsize: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._subs[investor_id].add(q)
        return q

    def unsubscribe(self, investor_id: str, q: asyncio.Queue) -> None:
        self._subs.get(investor_id, set()).discard(q)
        if investor_id in self._subs and not self._subs[investor_id]:
            self._subs.pop(investor_id, None)

    def publish(self, investor_id: str, event: dict) -> int:
        delivered = 0
        for q in list(self._subs.get(investor_id, ())):
            try:
                q.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                # Slow consumer — drop. The REST feed remains source of truth.
                pass
        return delivered

    def subscriber_count(self, investor_id: str) -> int:
        return len(self._subs.get(investor_id, set()))


PUBSUB = PubSub()
