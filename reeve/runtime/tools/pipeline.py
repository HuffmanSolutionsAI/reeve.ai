from __future__ import annotations

from ...sourcing.duckdb_pipeline import PipelineFilter, query_pipeline
from ..capability import Tier
from ..tool import tool


@tool(
    "query_sourcing_pipeline",
    Tier.READ,
    {
        "type": "object",
        "properties": {
            "min_units": {"type": "integer", "minimum": 1},
            "max_units": {"type": "integer", "minimum": 1},
            "min_ask": {"type": "number"},
            "max_ask": {"type": "number"},
            "market": {
                "type": "string",
                "description": "City or state, case-insensitive substring match.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "additionalProperties": False,
    },
    (
        "Query the DuckDB/Parquet distressed-property sourcing pipeline. "
        "Returns candidate properties matching the filter, ordered by ask asc."
    ),
    reads=["duckdb_pipeline"],
)
async def query_sourcing_pipeline(
    min_units: int | None = None,
    max_units: int | None = None,
    min_ask: float | None = None,
    max_ask: float | None = None,
    market: str | None = None,
    limit: int = 25,
) -> dict:
    f = PipelineFilter(
        min_units=min_units,
        max_units=max_units,
        min_ask=min_ask,
        max_ask=max_ask,
        market=market,
        limit=limit,
    )
    return await query_pipeline(f)
