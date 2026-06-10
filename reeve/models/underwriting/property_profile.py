"""PropertyProfile — the physical truth of the asset.

The per-structure year_built is deliberate: a 1940 clubhouse and 1960
apartments age, depreciate, and carry abatement risk differently. The
condition_inventory drives the renovation budget shape; the site fields
feed the ancillary income inventory."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Sourced


class StructureType(str, Enum):
    APARTMENTS = "apartments"
    CLUBHOUSE = "clubhouse"
    GARAGE = "garage"
    LAUNDRY = "laundry"
    OTHER = "other"


class Structure(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    label: str                                      # "main building", "clubhouse"
    structure_type: StructureType = StructureType.APARTMENTS
    year_built: int                                 # required — drives abatement + contingency
    units_count: int = Field(ge=0, default=0)
    notes: str | None = None


class UnitMix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beds: int = Field(ge=0)
    baths: float = Field(ge=0)                      # 1.5, 2.5
    count: int = Field(ge=0)
    avg_sqft: float | None = None


class ConditionInventory(BaseModel):
    """Tier counts. Sum equals total units. Per-unit detail lives on the
    rent-roll row (LeaseRow.condition_tier)."""
    model_config = ConfigDict(extra="forbid")
    renovated: int = Field(ge=0, default=0)
    rent_ready: int = Field(ge=0, default=0)
    down: int = Field(ge=0, default=0)


class CompletedCapital(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str                                       # "roof replacement"
    year: int | None = None
    cost: float | None = None
    verified: bool = False                          # if false, treat as broker claim


class Site(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parking_spaces: int | None = None
    parking_scarce: bool = False                    # ancillary income lever (paid parking)
    storage_dead_space: bool = False                # storage-rental opportunity
    standalone_structures: list[str] = Field(default_factory=list)


class PropertyProfile(BaseModel):
    """Embedded on Deal."""
    model_config = ConfigDict(extra="forbid")

    structures: list[Structure] = Field(default_factory=list)
    unit_mix: list[UnitMix] = Field(default_factory=list)
    physical_occupancy: Sourced[float] | None = None  # 0..1
    condition_inventory: ConditionInventory = Field(default_factory=ConditionInventory)
    completed_capital: list[CompletedCapital] = Field(default_factory=list)
    site: Site = Field(default_factory=Site)
    submarket: str | None = None
    demand_drivers: list[str] = Field(default_factory=list)

    # ---- derived helpers (do not mutate; compute on the fly) -------------
    @property
    def total_units(self) -> int:
        return sum(s.units_count for s in self.structures) or sum(m.count for m in self.unit_mix)

    @property
    def oldest_year_built(self) -> int | None:
        years = [s.year_built for s in self.structures if s.year_built]
        return min(years) if years else None

    @property
    def has_pre_1980_structure(self) -> bool:
        y = self.oldest_year_built
        return y is not None and y < 1980
