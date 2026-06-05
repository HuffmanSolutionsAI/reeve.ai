"""Seed comp data for sample markets.

This is the reference comp source for v1. The lookup interface is what
matters — wiring a real API (RentCast, HouseCanary) replaces this dict
without touching the tool surface."""
from __future__ import annotations

import re


SEED_COMPS: dict[str, dict] = {
    "westfield_07090": {
        "market_key": "westfield_07090",
        "city": "Westfield", "state": "NJ", "zip": "07090",
        "avg_market_rent": 1466,
        "rent_per_sqft": 1.85,
        "median_price_per_unit": 165000,
        "sale_cap_low": 0.058, "sale_cap_high": 0.072,
        "sample_size": 24,
        "as_of": "2026-05",
    },
    "summit_07901": {
        "market_key": "summit_07901",
        "city": "Summit", "state": "NJ", "zip": "07901",
        "avg_market_rent": 1825,
        "rent_per_sqft": 2.20,
        "median_price_per_unit": 215000,
        "sale_cap_low": 0.050, "sale_cap_high": 0.062,
        "sample_size": 18,
        "as_of": "2026-05",
    },
    "trenton_08611": {
        "market_key": "trenton_08611",
        "city": "Trenton", "state": "NJ", "zip": "08611",
        "avg_market_rent": 1190,
        "rent_per_sqft": 1.35,
        "median_price_per_unit": 78000,
        "sale_cap_low": 0.085, "sale_cap_high": 0.105,
        "sample_size": 31,
        "as_of": "2026-05",
    },
    "columbus_43215": {
        "market_key": "columbus_43215",
        "city": "Columbus", "state": "OH", "zip": "43215",
        "avg_market_rent": 1325,
        "rent_per_sqft": 1.55,
        "median_price_per_unit": 92000,
        "sale_cap_low": 0.072, "sale_cap_high": 0.085,
        "sample_size": 27,
        "as_of": "2026-05",
    },
}


_ZIP_RE = re.compile(r"\b(\d{5})\b")


def lookup_market_key(address: str) -> str | None:
    """Best-effort match of an address to a seed market.

    Order: ZIP exact > city substring. Returns None if no match — the tool
    surfaces that to the agent so confidence drops."""
    lower = address.lower()
    zip_match = _ZIP_RE.search(address)
    zip_code = zip_match.group(1) if zip_match else None
    if zip_code:
        for key, data in SEED_COMPS.items():
            if data["zip"] == zip_code:
                return key
    for key, data in SEED_COMPS.items():
        if data["city"].lower() in lower:
            return key
    return None
