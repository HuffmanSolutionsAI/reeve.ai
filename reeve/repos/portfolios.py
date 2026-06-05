from __future__ import annotations

from ..db.mongo import COLLECTIONS, db
from ..models.portfolio import Portfolio


async def list_portfolios(investor_id: str) -> list[Portfolio]:
    cursor = db()[COLLECTIONS["portfolios"]].find(
        {"investor_id": investor_id}
    ).sort([("created_at", 1)])
    return [Portfolio.model_validate(doc) async for doc in cursor]


async def create_portfolio(investor_id: str, name: str) -> Portfolio:
    portfolio = Portfolio(investor_id=investor_id, name=name)
    await db()[COLLECTIONS["portfolios"]].insert_one(portfolio.model_dump(by_alias=True))
    return portfolio


async def get_or_create_default_portfolio(
    investor_id: str, default_name: str = "Main Portfolio"
) -> tuple[Portfolio, bool]:
    """Find the investor's first portfolio (oldest) or create one named
    `default_name`. Returns (portfolio, was_created)."""
    existing = await list_portfolios(investor_id)
    if existing:
        return existing[0], False
    return await create_portfolio(investor_id, default_name), True
