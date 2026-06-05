"""DuckDB query against the seed sourcing pipeline.

The seed lives at `data/sourcing_seed.json`; DuckDB reads it natively
through `read_json_auto`. The production version of this tool reads from
S3-backed Parquet — only the path string changes. All predicates use
parameter binding so the agent's structured filter is never spliced into
SQL."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEED_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "sourcing_seed.json"


@dataclass
class PipelineFilter:
    min_units: int | None = None
    max_units: int | None = None
    min_ask: float | None = None
    max_ask: float | None = None
    market: str | None = None  # matches city or state, case-insensitive
    limit: int = 25

    def __post_init__(self) -> None:
        if self.limit < 1:
            self.limit = 1
        if self.limit > 100:
            self.limit = 100


def _build_where(f: PipelineFilter) -> tuple[str, list[Any]]:
    preds: list[str] = []
    params: list[Any] = []
    if f.min_units is not None:
        preds.append("units >= ?")
        params.append(int(f.min_units))
    if f.max_units is not None:
        preds.append("units <= ?")
        params.append(int(f.max_units))
    if f.min_ask is not None:
        preds.append("ask >= ?")
        params.append(float(f.min_ask))
    if f.max_ask is not None:
        preds.append("ask <= ?")
        params.append(float(f.max_ask))
    if f.market:
        preds.append("(LOWER(city) LIKE ? OR LOWER(state) LIKE ?)")
        like = f"%{f.market.lower()}%"
        params.extend([like, like])
    where = " AND ".join(preds) if preds else "TRUE"
    return where, params


def _query_sync(f: PipelineFilter, seed_path: Path) -> dict:
    if not seed_path.exists():
        return {"candidates": [], "count": 0, "filter": f.__dict__, "note": "seed missing"}

    import duckdb

    con = duckdb.connect(":memory:")
    where, params = _build_where(f)
    sql = (
        f"SELECT address, city, state, zip, units, ask, year_built, distress_signal "
        f"FROM read_json_auto('{seed_path}') "
        f"WHERE {where} ORDER BY ask LIMIT ?"
    )
    params.append(f.limit)
    cursor = con.execute(sql, params)
    cols = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    candidates = [dict(zip(cols, r)) for r in rows]
    return {
        "candidates": candidates,
        "count": len(candidates),
        "filter": f.__dict__,
        "source": str(seed_path.name),
    }


async def query_pipeline(
    f: PipelineFilter, *, seed_path: Path | None = None
) -> dict:
    path = seed_path or SEED_JSON
    return await asyncio.to_thread(_query_sync, f, path)
