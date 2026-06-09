"""Seed Mongo with a sample investor + portfolio + deals so the UI has
something to render.

Usage:
    MONGO_URI=mongodb://localhost:27017 PYTHONPATH=. python3 scripts/seed_dev.py
Outputs the investor _id — put it in web/.env.development.local as
VITE_INVESTOR_ID for the UI."""
from __future__ import annotations

import asyncio
import json

from reeve.db.mongo import ensure_indexes
from reeve.models import (
    BuyBox,
    Building,
    Deal,
    DealSource,
    DealStatus,
    Financing,
    Investor,
    InvestorPreferences,
    Portfolio,
    Unit,
    UnitStatus,
)
from reeve.repos.deals import upsert_deal
from reeve.repos.investors import upsert_investor
from reeve.db.mongo import COLLECTIONS, db


DEMO_EMAIL = "james@oakwood.test"
DEMO_PASSWORD = "password123"


async def main() -> None:
    await ensure_indexes()

    from reeve.api.passwords import hash_password

    investor = Investor(
        name="James M.",
        entity_name="Oakwood Holdings",
        email=DEMO_EMAIL,
        password=hash_password(DEMO_PASSWORD),
        preferences=InvestorPreferences(address_as="James", verbosity="brief"),
        buy_box=BuyBox(
            cap_floor=0.07,
            min_dscr=1.20,
            target_coc=0.08,
            markets=["Westfield, NJ", "Summit, NJ", "Columbus, OH"],
        ),
    )
    await upsert_investor(investor)

    portfolio = Portfolio(investor_id=investor.id, name="Oakwood Portfolio")
    await db()[COLLECTIONS["portfolios"]].replace_one(
        {"_id": portfolio.id}, portfolio.model_dump(by_alias=True), upsert=True,
    )

    buildings_spec = [
        ("412 Lincoln St, Westfield, NJ", 4),
        ("27 South Ave, Westfield, NJ", 6),
        ("88 Springfield Ave, Summit, NJ", 10),
    ]
    for address, units_count in buildings_spec:
        building = Building(
            portfolio_id=portfolio.id, address=address, units_count=units_count,
            acquired_at="2024-01-01", basis=720000 + units_count * 50_000,
            financing=Financing(rate=0.0675, term=25, ltv=0.70),
        )
        await db()[COLLECTIONS["buildings"]].replace_one(
            {"_id": building.id}, building.model_dump(by_alias=True), upsert=True,
        )
        for i in range(units_count):
            unit = Unit(
                building_id=building.id,
                label=f"{(i // 2) + 1}{'AB'[i % 2]}",
                market_rent=1466,
                status=UnitStatus.OCCUPIED if i < units_count - 1 else UnitStatus.VACANT,
            )
            await db()[COLLECTIONS["units"]].replace_one(
                {"_id": unit.id}, unit.model_dump(by_alias=True), upsert=True,
            )

    deals_spec = [
        ("1423 Elmwood Ave, Westfield, NJ 07090", 8, 1_150_000, DealStatus.SOURCED),
        ("1804 Hamilton Ave, Trenton, NJ 08611", 12, 720_000, DealStatus.SOURCED),
        ("44 Olentangy River Rd, Columbus, OH 43215", 14, 1_380_000, DealStatus.ANALYZED),
    ]
    for addr, units, ask, status in deals_spec:
        deal = Deal(
            investor_id=investor.id, address=addr, units=units, ask=ask,
            source=DealSource.SAM, status=status,
        )
        await upsert_deal(deal)

    print(json.dumps({
        "investor_id": investor.id,
        "portfolio_id": portfolio.id,
        "login_email": DEMO_EMAIL,
        "login_password": DEMO_PASSWORD,
    }, indent=2))
    print(f"\nLog in at the UI with {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
