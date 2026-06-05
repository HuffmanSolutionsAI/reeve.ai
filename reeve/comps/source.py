"""Comp lookup with a Mongo-backed TTL cache (`comps` collection).

Cache key = `market_key` (e.g. 'westfield_07090'). A hit avoids the seed
read (and, in a real impl, the paid API call). Expired entries are ignored
and replaced."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..db.mongo import COLLECTIONS, db
from ..models.base import now_iso
from ..models.stubs import Comp
from .seed import SEED_COMPS, lookup_market_key


CACHE_TTL_HOURS = 24


def _expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=CACHE_TTL_HOURS)).isoformat()


def _is_fresh(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    except ValueError:
        return False


async def lookup_comps(address: str) -> dict:
    """Return comp data for an address. Result shape:
        {
          "market_key": str | None,
          "matched": bool,
          "address": str,
          "comps": {...} | None,   # the seed/cached record
          "source": "cache" | "seed" | "miss",
          "fetched_at": ISO,
        }
    Misses (unknown market) return matched=False with comps=None so the
    agent can lower confidence rather than fabricate a number."""
    market_key = lookup_market_key(address)
    if market_key is None:
        return {
            "market_key": None,
            "matched": False,
            "address": address,
            "comps": None,
            "source": "miss",
            "fetched_at": now_iso(),
        }

    coll = db()[COLLECTIONS["comps"]]
    cached = await coll.find_one({"area_key": market_key})
    if cached and _is_fresh(cached.get("expires_at")):
        return {
            "market_key": market_key,
            "matched": True,
            "address": address,
            "comps": cached["payload"],
            "source": "cache",
            "fetched_at": cached.get("updated_at"),
        }

    payload = dict(SEED_COMPS[market_key])
    comp = Comp(
        area_key=market_key,
        payload=payload,
        expires_at=_expiry(),
    )
    doc = comp.model_dump(by_alias=True)
    await coll.replace_one({"area_key": market_key}, doc, upsert=True)
    return {
        "market_key": market_key,
        "matched": True,
        "address": address,
        "comps": payload,
        "source": "seed",
        "fetched_at": comp.updated_at,
    }
