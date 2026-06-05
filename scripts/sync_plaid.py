"""Sync Plaid transactions (mock for dev) for every building belonging to
an investor. Idempotent — re-runs just upsert by plaid_id.

Usage:
    PYTHONPATH=. python scripts/sync_plaid.py --investor <id> [--days 60]
"""
from __future__ import annotations

import argparse
import asyncio

from reeve.db.mongo import COLLECTIONS, db, ensure_indexes
from reeve.finance.plaid import MockPlaidClient, sync_transactions
from reeve.finance.seed import synthesize_transactions


async def main(investor_id: str, days: int) -> None:
    await ensure_indexes()

    portfolio_ids: list[str] = []
    async for p in db()[COLLECTIONS["portfolios"]].find({"investor_id": investor_id}):
        portfolio_ids.append(p["_id"])
    if not portfolio_ids:
        print(f"no portfolios for investor {investor_id!r}")
        return

    grand_total = 0
    async for b in db()[COLLECTIONS["buildings"]].find({"portfolio_id": {"$in": portfolio_ids}}):
        units_count = b.get("units_count") or 0
        sample = await db()[COLLECTIONS["units"]].find_one(
            {"building_id": b["_id"], "market_rent": {"$exists": True, "$ne": None}}
        )
        rent = float(sample["market_rent"]) if sample else 1500.0
        fixtures = synthesize_transactions(
            building_id=b["_id"], units=units_count, market_rent=rent, days=days,
        )
        client = MockPlaidClient(fixtures=fixtures)
        ptxns = client.fetch_transactions(
            f"acct-{b['_id']}", since="1970-01-01", until="9999-12-31",
        )
        n = await sync_transactions(
            investor_id=investor_id, building_id=b["_id"], plaid_txns=ptxns,
        )
        print(f"  {b['address']}: {n} txns")
        grand_total += n

    print(f"total: {grand_total}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--investor", required=True, help="investor _id")
    p.add_argument("--days", type=int, default=60)
    args = p.parse_args()
    asyncio.run(main(args.investor, args.days))
