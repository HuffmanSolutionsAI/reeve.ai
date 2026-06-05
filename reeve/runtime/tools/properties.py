"""Reeve's property lifecycle: add, update, remove.

All three are ACT_INTERNAL (reversible-ish, no money/legal/tenant). The
remove tool reads `lease` and `transaction` (sensitive) to count
dependencies before deleting, so each call audits those scopes."""
from __future__ import annotations

from ...db.mongo import COLLECTIONS, db
from ...models.building import Building, Financing
from ...models.unit import UnitStatus
from ...repos.buildings import (
    create_building,
    delete_building,
    find_building_by_address,
    get_building,
    update_building_fields,
)
from ...repos.portfolios import (
    create_portfolio,
    get_or_create_default_portfolio,
    list_portfolios,
)
from ...repos.units import (
    create_units_bulk,
    delete_units_for_building,
    generate_unit_labels,
    list_unit_ids_for_building,
)
from ..capability import Tier
from ..spec import RunContext
from ..tool import tool


async def _resolve_building(
    investor_id: str,
    address: str | None,
    building_id: str | None,
) -> Building | None:
    """Look up a building by id or by address, scoped to the investor.
    Returns None if not found or if the id belongs to another investor."""
    if building_id:
        building = await get_building(building_id)
        if building is None:
            return None
        portfolio_doc = await db()[COLLECTIONS["portfolios"]].find_one(
            {"_id": building.portfolio_id}, projection={"investor_id": 1}
        )
        if not portfolio_doc or portfolio_doc.get("investor_id") != investor_id:
            return None
        return building
    if address:
        return await find_building_by_address(investor_id, address)
    return None


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


@tool(
    "update_property",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Address used to find the building. Either this or building_id is required.",
            },
            "building_id": {"type": "string"},
            "new_address": {
                "type": "string",
                "description": "Replace the building's stored address. Only set if you want to rename it.",
            },
            "acquired_at": {"type": "string", "description": "ISO date."},
            "basis": {"type": "number", "minimum": 0, "description": "Cost basis in dollars."},
            "financing": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "rate": {"type": "number", "minimum": 0},
                    "term": {"type": "integer", "minimum": 1},
                    "ltv": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "description": "Replaces the existing financing block as a whole (not a partial patch within financing).",
            },
        },
        "additionalProperties": False,
    },
    (
        "Update a building's metadata: address (rename), acquired_at, basis, "
        "or financing. Partial — only the fields you pass are written; "
        "others stay untouched. Doesn't add or remove units — use the add_unit / "
        "remove_unit tools (when wired) for that."
    ),
    reads=["building"],
    writes=["update_building"],
    needs_ctx=True,
)
async def update_property(
    _ctx: RunContext,
    address: str | None = None,
    building_id: str | None = None,
    new_address: str | None = None,
    acquired_at: str | None = None,
    basis: float | None = None,
    financing: dict | None = None,
) -> dict:
    if not address and not building_id:
        return {
            "updated": False,
            "reason": "must provide either `address` or `building_id`",
        }

    building = await _resolve_building(_ctx.investor_id, address, building_id)
    if building is None:
        return {"updated": False, "reason": "building not found"}

    patch: dict[str, object] = {}
    if new_address is not None:
        patch["address"] = new_address
    if acquired_at is not None:
        patch["acquired_at"] = acquired_at
    if basis is not None:
        patch["basis"] = basis
    if financing is not None:
        patch["financing"] = Financing(**financing).model_dump()

    if not patch:
        return {
            "updated": False,
            "reason": "no fields to update — pass at least one of new_address, acquired_at, basis, financing",
        }

    updated = await update_building_fields(building.id, **patch)
    if updated is None:
        return {"updated": False, "reason": "update failed"}

    return {
        "updated": True,
        "building_id": building.id,
        "address": updated.address,
        "changed": sorted(patch.keys()),
    }


@tool(
    "remove_property",
    Tier.ACT_INTERNAL,
    {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "Address used to find the building. Either this or building_id is required.",
            },
            "building_id": {"type": "string"},
            "force": {
                "type": "boolean",
                "description": (
                    "Set true to remove the building even if it has leases "
                    "or transactions on file (they will be deleted too). "
                    "Without this, the tool reports the dependencies and "
                    "refuses."
                ),
            },
        },
        "additionalProperties": False,
    },
    (
        "Remove a building and its units. If leases or transactions reference "
        "the building's units, refuses with a count of each — call again "
        "with force=true to cascade-delete those rows too. Audit captures "
        "the sensitive reads on `lease` and `transaction`."
    ),
    reads=["building", "unit", "lease", "transaction"],
    writes=["remove_property"],
    needs_ctx=True,
)
async def remove_property(
    _ctx: RunContext,
    address: str | None = None,
    building_id: str | None = None,
    force: bool = False,
) -> dict:
    if not address and not building_id:
        return {
            "removed": False,
            "reason": "must provide either `address` or `building_id`",
        }

    building = await _resolve_building(_ctx.investor_id, address, building_id)
    if building is None:
        return {"removed": False, "reason": "building not found"}

    unit_ids = await list_unit_ids_for_building(building.id)
    lease_count = (
        await db()[COLLECTIONS["leases"]].count_documents(
            {"unit_id": {"$in": unit_ids}}
        )
        if unit_ids else 0
    )
    transaction_count = await db()[COLLECTIONS["transactions"]].count_documents(
        {"building_id": building.id}
    )

    if not force and (lease_count > 0 or transaction_count > 0):
        return {
            "removed": False,
            "address": building.address,
            "building_id": building.id,
            "dependencies": {
                "units": len(unit_ids),
                "leases": lease_count,
                "transactions": transaction_count,
            },
            "hint": (
                f"{building.address} has {lease_count} lease(s) and "
                f"{transaction_count} transaction(s). Re-call with force=true "
                f"to delete them along with the building, or handle the "
                f"dependencies first."
            ),
        }

    deleted: dict[str, int] = {}
    deleted["leases"] = (
        (await db()[COLLECTIONS["leases"]].delete_many(
            {"unit_id": {"$in": unit_ids}}
        )).deleted_count
        if unit_ids else 0
    )
    deleted["transactions"] = (
        (await db()[COLLECTIONS["transactions"]].delete_many(
            {"building_id": building.id}
        )).deleted_count
        if force else 0
    )
    deleted["units"] = await delete_units_for_building(building.id)
    deleted["buildings"] = await delete_building(building.id)

    return {
        "removed": True,
        "building_id": building.id,
        "address": building.address,
        "deleted": deleted,
    }
