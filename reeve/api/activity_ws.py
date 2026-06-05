"""Activity feed push over WebSocket.

Browsers can't set Authorization headers on WebSocket connections, so
the bearer token comes as a query param. Trade-off: tokens may end up in
server access logs — turn that off (or scrub `token=` from log lines)
before any non-dev deployment.

Protocol:
  - client connects ws://…/api/activity/stream?token=<jwt>
  - server validates the token, subscribes the client to the investor's
    pub/sub queue, and forwards every audit event as JSON.
  - on disconnect or auth failure, server unsubscribes and closes."""
from __future__ import annotations

import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .auth import AuthError, decode_token
from .pubsub import PUBSUB


router = APIRouter()


@router.websocket("/activity/stream")
async def activity_stream(ws: WebSocket, token: str = Query(...)) -> None:
    try:
        claims = decode_token(token)
    except AuthError as e:
        await ws.close(code=4401, reason=e.detail)
        return
    investor_id = claims.get("investor_id")
    if not investor_id:
        await ws.close(code=4401, reason="no investor_id in token")
        return

    await ws.accept()
    queue = PUBSUB.subscribe(investor_id)
    try:
        # Announce the subscription so the client can confirm the stream is live.
        await ws.send_text(json.dumps({"event": "subscribed", "investor_id": investor_id}))
        while True:
            event = await queue.get()
            await ws.send_text(json.dumps(event, default=str))
    except WebSocketDisconnect:
        pass
    finally:
        PUBSUB.unsubscribe(investor_id, queue)
