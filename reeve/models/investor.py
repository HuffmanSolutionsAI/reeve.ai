from pydantic import BaseModel, Field

from .base import BaseDoc


class BuyBox(BaseModel):
    cap_floor: float | None = None
    min_dscr: float | None = None
    target_coc: float | None = None
    markets: list[str] = Field(default_factory=list)
    unit_range: tuple[int, int] | None = None
    price_range: tuple[float, float] | None = None


class InvestorPreferences(BaseModel):
    address_as: str | None = None
    autonomy_thresholds: dict = Field(default_factory=dict)
    brief_cadence: str | None = None
    verbosity: str | None = None


class Investor(BaseDoc):
    name: str
    entity_name: str | None = None
    # Auth — both optional so legacy/seeded investors still load. `password`
    # holds a PHC-style hash (pbkdf2_sha256$iters$salt$hash); it is NEVER
    # serialized into an API response (see api.auth_endpoints.public_dict).
    email: str | None = None
    password: str | None = None
    preferences: InvestorPreferences = Field(default_factory=InvestorPreferences)
    buy_box: BuyBox = Field(default_factory=BuyBox)
    entity_structure_id: str | None = None  # stub link to entity_struct (Tess)
