"""Per-field provenance for value-add underwriting inputs.

Every material input carries a Provenance tag. The engine treats them
differently:
  - VERIFIED inputs feed every state directly.
  - BROKER_CLAIMED inputs feed only the broker-pro-forma diff report,
    NOT the engine's NOI math. The engine also runs a haircut variant
    that substitutes conservative defaults for broker_claimed numbers
    and the gap to the headline result is reported.
  - ASSUMED inputs feed the math but appear in the risk register and
    drive the perturbation analysis that names the load-bearing
    assumption.

`Sourced` is the small envelope every material number wraps itself in.
Used as a Pydantic field type, it carries both the value and where it
came from."""
from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class Provenance(str, Enum):
    VERIFIED = "verified"           # third-party doc / quote / audit in hand
    BROKER_CLAIMED = "broker_claimed"  # came from the OM / listing / broker; adversarial
    ASSUMED = "assumed"             # agent or investor provided; a lever, not a fact


T = TypeVar("T")


class Sourced(BaseModel, Generic[T]):
    """A value plus its provenance + optional citation."""

    model_config = ConfigDict(use_enum_values=True)

    value: T
    prov: Provenance = Provenance.ASSUMED
    citation: str | None = None  # free-form: doc name, URL, "investor said in chat"
    as_of: str | None = None     # when the citation was current


def is_verified(s: Sourced | None) -> bool:
    return s is not None and (s.prov == Provenance.VERIFIED.value or s.prov == Provenance.VERIFIED)


def is_broker_claimed(s: Sourced | None) -> bool:
    return s is not None and (s.prov == Provenance.BROKER_CLAIMED.value or s.prov == Provenance.BROKER_CLAIMED)


def is_assumed(s: Sourced | None) -> bool:
    return s is not None and (s.prov == Provenance.ASSUMED.value or s.prov == Provenance.ASSUMED)
