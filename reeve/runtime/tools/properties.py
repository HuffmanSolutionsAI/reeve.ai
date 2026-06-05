"""Reeve's add_property tool: one call creates the building + N units +
(if needed) an initial portfolio for them to live under. Idempotent on
address — if the investor already has a building at the same address,
the tool refuses rather than silently creating a duplicate."""
from __future__ import annotations

from ...models.building import Building, Financing
from ...models.unit import UnitStatus
from ...repos.buildings import create_building, find_building_by_address
from ...repos.portfolios import (
    create_portfolio,
    get_or_create_default_portfolio,
    list_portfolios,
)
from ...repos.units import create_units_bulk, generate_unit_labels
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


@tool(
    "add_property",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Street address. Used to dedupe — same address won't be added twice.",
            },
            "units_count": {
                "type": "integer", "minimum": 1, "maximum": 200,
                "description": "Total unit count for the building.",
            },
            "portfolio_id": {
                "type": "string",
                "description": (
                    "Specific portfolio to add into. If omitted: use the "
                    "investor's existing portfolio (if exactly one), or "
                    "create a new one named `portfolio_name`."
                ),
            },
            "portfolio_name": {
                "type": "string",
                "description": (
                    "Name for a new portfolio if one needs creating. "
                    "Default 'Main Portfolio'. Ignored if portfolio_id is "
                    "passed or an existing portfolio is reused."
                ),
            },
            "acquired_at": {
                "type": "string",
                "description": "ISO date of acquisition. Optional.",
            },
            "basis": {
                "type": "number", "minimum": 0,
                "description": "Purchase basis (cost basis) in dollars. Optional.",
            },
            "financing": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rate": {"type": "number", "minimum": 0},
                    "term": {"type": "integer", "minimum": 1},
                    "ltv": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "description": "Optional financing — rate (decimal), term (years), LTV (decimal).",
            },
            "unit_labels": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "Custom labels for the units. Length must match "
                    "units_count. If omitted, labels are auto-generated "
                    "as 1A, 1B, 2A, 2B, … using units_per_floor."
                ),
            },
            "units_per_floor": {
                "type": "integer", "minimum": 1, "maximum": 26,
                "description": "Used for auto-label generation. Default 2.",
            },
            "market_rent": {
                "type": "number", "minimum": 0,
                "description": "Per-unit market rent baseline (applied to every unit).",
            },
            "initial_status": {
                "enum": ["occupied", "vacant", "turn"],
                "description": "Status for all units. Default 'vacant'.",
            },
        },
        "required": ["address", "units_count"],
        "additionalProperties": False,
    },
    (
        "Add a property to the investor's portfolio. Creates a building at "
        "`address` with `units_count` units (auto-labeled 1A/1B/2A/2B/… "
        "unless overridden), under the investor's existing portfolio or a "
        "new one. Refuses if a building at the same address already exists."
    ),
    reads=["investor", "portfolio", "building"],
    writes=["create_portfolio", "create_building", "create_unit"],
    needs_ctx=True,
)
async def add_property(
    _ctx: RunContext,
    address: str,
    units_count: int,
    portfolio_id: str | None = None,
    portfolio_name: str = "Main Portfolio",
    acquired_at: str | None = None,
    basis: float | None = None,
    financing: dict | None = None,
    unit_labels: list[str] | None = None,
    units_per_floor: int = 2,
    market_rent: float | None = None,
    initial_status: str = "vacant",
) -> dict:
    # 1) Dedupe by address across the investor's pipeline.
    existing = await find_building_by_address(_ctx.investor_id, address)
    if existing is not None:
        return {
            "added": False,
            "reason": (
                f"A building at {address!r} already exists "
                f"(id={existing.id[:8]}…). Use a different address or "
                f"remove the existing one first."
            ),
        }

    # 2) Resolve portfolio.
    portfolio_created = False
    if portfolio_id:
        portfolios = await list_portfolios(_ctx.investor_id)
        portfolio = next((p for p in portfolios if p.id == portfolio_id), None)
        if portfolio is None:
            return {
                "added": False,
                "reason": f"portfolio {portfolio_id!r} not found in this investor's account.",
            }
    else:
        portfolio, portfolio_created = await get_or_create_default_portfolio(
            _ctx.investor_id, default_name=portfolio_name,
        )

    # 3) Generate unit labels (or use the caller's).
    if unit_labels is None:
        labels = generate_unit_labels(units_count, units_per_floor)
    else:
        if len(unit_labels) != units_count:
            return {
                "added": False,
                "reason": (
                    f"unit_labels length ({len(unit_labels)}) doesn't "
                    f"match units_count ({units_count})."
                ),
            }
        labels = list(unit_labels)

    # 4) Build and persist the Building + Units.
    building = Building(
        portfolio_id=portfolio.id,
        address=address,
        units_count=units_count,
        acquired_at=acquired_at,
        basis=basis,
        financing=Financing(**financing) if financing else None,
    )
    await create_building(building)

    try:
        status_enum = UnitStatus(initial_status)
    except ValueError:
        status_enum = UnitStatus.VACANT

    units = await create_units_bulk(
        building_id=building.id,
        labels=labels,
        market_rent=market_rent,
        initial_status=status_enum,
    )

    return {
        "added": True,
        "portfolio": {
            "id": portfolio.id,
            "name": portfolio.name,
            "created": portfolio_created,
        },
        "building": {
            "id": building.id,
            "address": building.address,
            "units_count": building.units_count,
            "acquired_at": building.acquired_at,
            "basis": building.basis,
        },
        "units": [{"id": u.id, "label": u.label} for u in units],
        "summary": (
            f"Added {address} ({units_count} unit{'s' if units_count != 1 else ''}, "
            f"labels {' '.join(labels)}) to portfolio {portfolio.name!r}"
            + (" (created)" if portfolio_created else "")
            + "."
        ),
    }
