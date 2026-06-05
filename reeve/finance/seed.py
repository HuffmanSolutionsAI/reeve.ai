"""Synthetic Plaid-shaped transactions for dev/smoke.

Generates a realistic month-over-month pattern: rent receipts on the 1st,
mortgage on the 5th, insurance on the 10th, property mgmt on the 15th, and
a handful of maintenance hits at random days. Deterministic by `seed`."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone


_MAINTENANCE_DESCRIPTIONS = [
    ("Plumbing repair - kitchen sink", "ACME Plumbing"),
    ("HVAC service call", "Cool Air HVAC"),
    ("Electrical repair - outlet", "Bright Electric"),
    ("Tile replacement - bath", "Hometile Pros"),
    ("Window pane replacement", "GlassWorks"),
    ("Paint touch-up common areas", "Brushstroke"),
    ("Snow removal", "WinterScape"),
]


def _between(d: date, start: date, end: date) -> bool:
    return start <= d <= end


def synthesize_transactions(
    *,
    building_id: str,
    units: int,
    market_rent: float,
    days: int = 60,
    seed: int | None = 7,
    today: date | None = None,
) -> list[dict]:
    rng = random.Random(seed)
    end = today or datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    txns: list[dict] = []

    rent_in_place = round(market_rent * 0.85, 2)
    monthly_mortgage = round(market_rent * units * 0.45, 2)
    monthly_insurance = round(market_rent * units * 0.04, 2)
    monthly_mgmt = round(market_rent * units * 0.08, 2)

    cur = start
    while cur <= end:
        iso = cur.isoformat()
        if cur.day == 1:
            for u in range(units):
                label = f"{(u // 2) + 1}{'AB'[u % 2]}"
                txns.append({
                    "plaid_id": f"rent-{building_id}-{label}-{iso}",
                    "account_id": f"acct-{building_id}",
                    "date": iso,
                    "amount": rent_in_place,
                    "description": f"Rent payment unit {label}",
                    "merchant": "Tenant ACH",
                    "plaid_category": ["Transfer", "Deposit"],
                })
        if cur.day == 5:
            txns.append({
                "plaid_id": f"mortgage-{building_id}-{iso}",
                "account_id": f"acct-{building_id}",
                "date": iso,
                "amount": -monthly_mortgage,
                "description": "Mortgage payment - principal and interest",
                "merchant": "First National Bank",
                "plaid_category": ["Payment", "Loan"],
            })
        if cur.day == 10:
            txns.append({
                "plaid_id": f"insurance-{building_id}-{iso}",
                "account_id": f"acct-{building_id}",
                "date": iso,
                "amount": -monthly_insurance,
                "description": "Property insurance premium",
                "merchant": "Liberty Mutual",
                "plaid_category": ["Service", "Insurance"],
            })
        if cur.day == 15:
            txns.append({
                "plaid_id": f"mgmt-{building_id}-{iso}",
                "account_id": f"acct-{building_id}",
                "date": iso,
                "amount": -monthly_mgmt,
                "description": "Property management fee",
                "merchant": "Cornerstone Property Mgmt",
                "plaid_category": ["Service", "Real Estate"],
            })
        cur += timedelta(days=1)

    n_maint = rng.randint(3, 6)
    for _ in range(n_maint):
        d = start + timedelta(days=rng.randint(0, days - 1))
        descr, merchant = rng.choice(_MAINTENANCE_DESCRIPTIONS)
        amt = -rng.choice([180, 240, 420, 850, 1200, 2400])
        txns.append({
            "plaid_id": f"maint-{building_id}-{d.isoformat()}-{rng.randint(1000, 9999)}",
            "account_id": f"acct-{building_id}",
            "date": d.isoformat(),
            "amount": amt,
            "description": descr,
            "merchant": merchant,
            "plaid_category": ["Service", "Home Improvement"],
        })

    txns.sort(key=lambda t: t["date"])
    return txns
