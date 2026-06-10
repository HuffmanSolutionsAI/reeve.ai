"""MarketContext — comps, caps, vacancy norms. Embedded on Deal.

Comps are SEGMENTED BY CONDITION. A renovated comp set supports the
target rent; classic comps support in-place sanity checks. Blending them
is how target rents get inflated."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .provenance import Sourced


class CompCondition(str, Enum):
    RENOVATED = "renovated"
    CLASSIC = "classic"
    UNKNOWN = "unknown"


class RentComp(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid")
    address: str | None = None
    condition: CompCondition = CompCondition.UNKNOWN
    beds: int
    baths: float
    rent: float
    sqft: float | None = None
    source: str | None = None
    observed_at: str | None = None


class CapRates(BaseModel):
    """Market cap by class. The class-appropriate cap is the floor-value
    divisor; the deal's exit cap is an *assumption* tested against this."""
    model_config = ConfigDict(extra="forbid")
    class_a: float | None = None
    class_b: float | None = None
    class_c: float | None = None
    source: str | None = None
    as_of: str | None = None

    def for_class(self, asset_class: str) -> float | None:
        return {"a": self.class_a, "b": self.class_b, "c": self.class_c}.get(
            asset_class.lower()
        )


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rent_comps: list[RentComp] = Field(default_factory=list)
    cap_rates: CapRates = Field(default_factory=CapRates)
    asset_class: str = "c"              # rough quality tier — picks the right market cap
    vacancy_norm: Sourced[float] | None = None
    rent_growth_trend: Sourced[float] | None = None

    # ---- helpers --------------------------------------------------------
    def renovated_comp_stats(self, *, beds: int | None = None) -> tuple[int, float | None]:
        """(n, mean) for renovated comps, optionally filtered by bed count."""
        pool = [
            c.rent for c in self.rent_comps
            if (c.condition == CompCondition.RENOVATED.value
                or c.condition == CompCondition.RENOVATED)
            and (beds is None or c.beds == beds)
        ]
        if not pool:
            return 0, None
        return len(pool), round(sum(pool) / len(pool), 2)

    @property
    def market_cap(self) -> float | None:
        return self.cap_rates.for_class(self.asset_class)
