"""Pydantic mirror of `/contracts/tenant_message.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Channel(str, Enum):
    EMAIL = "email"
    SMS = "sms"


class Purpose(str, Enum):
    RENEWAL_NOTICE = "renewal_notice"
    RENT_REMINDER = "rent_reminder"
    MAINTENANCE_UPDATE = "maintenance_update"
    COMPLIANCE = "compliance"
    GENERAL = "general"


class TenantMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["tenant_message"] = "tenant_message"
    tenant_id: str
    tenant_name: str | None = None
    lease_id: str | None = None
    unit_id: str | None = None
    building_id: str | None = None
    channel: Channel
    to: str | None = None
    subject: str
    body: str
    purpose: Purpose
    sent_at: str | None = None
