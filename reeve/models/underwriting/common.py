"""DealProfile — routing flag on Deal.

`stabilized` keeps the v1 underwriter path (existing `deal_analysis`
contract, `% of EGI` opex model). `value_add` and `distressed` route to
the v2 engine (this package) and the `value_add_analysis` contract.

Deals created before this v2 model existed default to `stabilized` so
nothing breaks."""
from __future__ import annotations

from enum import Enum


class DealProfile(str, Enum):
    STABILIZED = "stabilized"
    VALUE_ADD = "value_add"
    DISTRESSED = "distressed"
