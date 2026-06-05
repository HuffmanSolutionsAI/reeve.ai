"""Pydantic mirror of `/contracts/listing.schema.json`."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Channel(str, Enum):
    ZILLOW = "zillow"
    APARTMENTS_COM = "apartments_com"
    CRAIGSLIST = "craigslist"
    FACEBOOK_MARKETPLACE = "facebook_marketplace"


class Listing(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    type: Literal["listing"] = "listing"
    unit_id: str
    unit_label: str | None = None
    building_id: str
    address: str | None = None
    asking_rent: float = Field(ge=0)
    deposit: float | None = None
    term_months: int | None = Field(default=12, ge=1, le=60)
    available_from: str
    headline: str
    description: str
    amenities: list[str] = Field(default_factory=list)
    channels: list[Channel] = Field(default_factory=list)
    posted_at: str | None = None
    listing_urls: dict[str, str] | None = None
