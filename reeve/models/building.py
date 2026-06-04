from pydantic import BaseModel

from .base import BaseDoc


class Financing(BaseModel):
    rate: float | None = None
    term: int | None = None
    ltv: float | None = None


class Building(BaseDoc):
    portfolio_id: str
    address: str
    units_count: int
    acquired_at: str | None = None
    basis: float | None = None
    financing: Financing | None = None
    source_deal_id: str | None = None  # deal that closed into this building
