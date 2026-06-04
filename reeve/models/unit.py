from enum import Enum

from .base import BaseDoc


class UnitStatus(str, Enum):
    OCCUPIED = "occupied"
    VACANT = "vacant"
    TURN = "turn"


class Unit(BaseDoc):
    building_id: str
    label: str
    market_rent: float | None = None
    status: UnitStatus = UnitStatus.VACANT
    current_lease_id: str | None = None
