from __future__ import annotations

from ..capability import Tier
from ..tool import tool


@tool(
    "query_sourcing_pipeline",
    Tier.READ,
    {
        "type": "object",
        "properties": {"filter": {"type": "string"}},
        "additionalProperties": False,
    },
    "Query the DuckDB/Parquet distressed-property sourcing pipeline.",
    reads=["duckdb_pipeline"],
)
async def query_sourcing_pipeline(filter: str = "") -> dict:
    return {"candidates": [], "filter": filter, "_stub": "DuckDB wired in step 3"}
