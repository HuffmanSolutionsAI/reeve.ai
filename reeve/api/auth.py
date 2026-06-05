"""JWT auth.

Tokens carry `{sub, investor_id, exp}`. The dev-token endpoint issues
one for any investor_id — replace with real password/SSO auth before
any non-dev deployment.

Every protected endpoint depends on `require_investor_id`, which decodes
the bearer token and returns the pinned investor_id. Endpoints that
take an entity id in the path must additionally verify that entity
belongs to the token's investor (the `_assert_*` helpers below)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status

from ..config import settings


class AuthError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def issue_token(investor_id: str, *, ttl_minutes: int | None = None) -> dict[str, Any]:
    ttl = ttl_minutes if ttl_minutes is not None else settings.jwt_ttl_minutes
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ttl)
    payload = {
        "sub": investor_id,
        "investor_id": investor_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ttl * 60,
        "investor_id": investor_id,
    }


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise AuthError("token expired")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"invalid token: {e}")


def require_investor_id(
    authorization: str | None = Header(default=None),
) -> str:
    if not authorization:
        raise AuthError("missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise AuthError("Authorization must be a Bearer token")
    token = authorization[7:].strip()
    claims = decode_token(token)
    investor_id = claims.get("investor_id")
    if not investor_id:
        raise AuthError("token has no investor_id claim")
    return investor_id


# ---- cross-checks ---------------------------------------------------------
# Used by endpoints that take an entity id in the path; the entity must
# belong to the token's investor. Each helper raises 404 (not 403) so we
# don't leak existence of out-of-scope entities.


async def _assert_proposal(proposal_id: str, investor_id: str) -> None:
    from ..proposals import get_client
    p = await get_client().get(proposal_id)
    if p is None or p.investor_id != investor_id:
        raise HTTPException(404, "proposal not found")


async def _assert_conversation(conversation_id: str, investor_id: str) -> None:
    from ..repos.conversations import get_conversation
    conv = await get_conversation(conversation_id)
    if conv is None or conv.investor_id != investor_id:
        raise HTTPException(404, "conversation not found")


async def _assert_artifact(artifact_id: str, investor_id: str) -> None:
    from ..db.mongo import COLLECTIONS, db
    doc = await db()[COLLECTIONS["artifacts"]].find_one(
        {"_id": artifact_id}, projection={"deal_id": 1, "produced_by": 1},
    )
    if doc is None:
        raise HTTPException(404, "artifact not found")
    deal_id = doc.get("deal_id")
    if deal_id is None:
        # Artifact has no deal link (e.g. tax_memo, morning_brief) — scope by
        # the producing agent_run's conversation, which sits under the investor.
        # In v1 we accept these; tighten if needed.
        return
    deal = await db()[COLLECTIONS["deals"]].find_one(
        {"_id": deal_id}, projection={"investor_id": 1},
    )
    if deal is None or deal.get("investor_id") != investor_id:
        raise HTTPException(404, "artifact not found")
