"""Auth endpoints — dev token issuance + identity echo.

`POST /api/auth/dev-token` is a dev convenience: it issues a token for
ANY investor_id without validating credentials. Replace with real
password / SSO before production. The endpoint is intentionally separate
from the rest so it can be disabled with a single import change."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..repos.investors import get_investor
from .auth import issue_token, require_investor_id


router = APIRouter()


class DevTokenRequest(BaseModel):
    investor_id: str


@router.post("/auth/dev-token")
async def dev_token(body: DevTokenRequest) -> dict:
    # Validate the investor exists; otherwise the token would be useless.
    investor = await get_investor(body.investor_id)
    if investor is None:
        raise HTTPException(404, f"investor {body.investor_id!r} not found")
    return issue_token(body.investor_id)


@router.get("/me")
async def me(investor_id: str = Depends(require_investor_id)) -> dict:
    investor = await get_investor(investor_id)
    if investor is None:
        # Token references a vanished investor — treat as 401 since the
        # holder's identity is no longer valid.
        from .auth import AuthError
        raise AuthError("investor in token no longer exists")
    return investor.model_dump(by_alias=True)
