"""Pydantic mirror of `/contracts/work_order.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Trade(str, Enum):
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    GENERAL = "general"
    PAINTING = "painting"
    LANDSCAPING = "landscaping"
    APPLIANCE = "appliance"
    ROOFING = "roofing"


class Priority(str, Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    STANDARD = "standard"
    LOW = "low"


class VendorContact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str | None = None
    phone: str | None = None


class WorkOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["work_order"] = "work_order"
    vendor_id: str
    vendor_name: str | None = None
    building_id: str
    building_address: str | None = None
    unit_id: str | None = None
    unit_label: str | None = None
    trade: Trade
    scope: str
    priority: Priority
    max_spend: float | None = None
    dispatched_at: str | None = None
    contact: VendorContact | None = None
