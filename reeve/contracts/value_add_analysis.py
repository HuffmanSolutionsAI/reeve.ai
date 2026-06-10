"""Pydantic mirror of `/contracts/value_add_analysis.schema.json`.

This is the artifact Ana v2 emits and the UI's value-add card renders.
The schema is the wire contract; this is the runtime validator + the
shape the engine's runner serializes into."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.artifact import Confidence


class NOIStateLabel(str, Enum):
    IN_PLACE = "in_place"
    STABILIZED = "stabilized"
    STABILIZED_PLUS_ANCILLARY = "stabilized_plus_ancillary"


class NOIStatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    state: NOIStateLabel
    gross_potential_income: float
    vacancy_loss: float = 0.0
    credit_loss: float = 0.0
    concession_loss: float = 0.0
    other_income: float = 0.0
    effective_gross_income: float
    opex_lines: dict[str, float] = Field(default_factory=dict)
    opex_total: float
    noi: float
    reserves: float = 0.0


class BrokerDiffLinePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: str
    broker: float | None = None
    engine: float | None = None
    delta: float | None = None


class NOIPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_place: NOIStatePayload
    stabilized: NOIStatePayload
    stabilized_plus_ancillary: NOIStatePayload
    broker_proforma_diff: list[BrokerDiffLinePayload] = Field(default_factory=list)


class BidLadder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opening: float
    target_bid: float
    walk_away: float


class ValuationPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    floor_value: float
    stabilized_value: float
    cost_to_stabilize: float | None = None
    required_margin_dollars: float | None = None
    ceiling_max_offer: float
    bid_ladder: BidLadder


class SourcesAndUses(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bridge_basis: float
    bridge_proceeds: float
    bridge_equity_in: float
    bridge_annual_interest: float | None = None
    perm_by_ltv: float | None = None
    perm_by_dscr: float | None = None
    perm_loan: float
    perm_annual_ds: float | None = None
    refi_costs: float | None = None
    refi_proceeds_net: float | None = None
    equity_recapture: float | None = None
    residual_equity: float | None = None
    structure: Literal["bridge_to_perm", "perm_first", "bridge_only", "all_cash", "no_perm"]
    perm_first_qualifies: bool | None = None
    occupancy_gate_pct: float | None = None


class Returns(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stabilized_cash_on_cash: float
    perm_dscr_at_stabilized: float | None = None
    hold_period_irr: float | None = None


class CrossCheckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: float
    status: Literal["pass", "warn", "fail"]
    detail: str | None = None


class SensitivityCellPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_rent_delta_pct: float
    exit_cap_delta_bps: float
    target_rent_used_avg: float | None = None
    exit_cap_used: float | None = None
    stabilized_noi: float | None = None
    max_offer: float


class SensitivityPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    swing: float
    cells: list[SensitivityCellPayload]


class AssumptionRiskPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str
    provenance: Literal["verified", "broker_claimed", "assumed"]
    value_used: float
    perturbation_pct: float | None = None
    max_offer_low: float | None = None
    max_offer_high: float | None = None
    swing_dollars: float
    verification_action: str | None = None


class FlagPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    severity: Literal["blocking", "watch"]
    text: str
    unblock_action: str | None = None


class VerdictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["pursue", "pass", "conditional"]
    max_price: float
    headline: str


class ValueAddAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    type: Literal["value_add_analysis"] = "value_add_analysis"
    deal_id: str
    address: str
    units: int = Field(ge=1)
    as_of: str | None = None
    noi_panel: NOIPanel
    valuation_panel: ValuationPanel
    sources_and_uses: SourcesAndUses
    returns: Returns
    cross_checks: list[CrossCheckPayload]
    sensitivity: SensitivityPanel
    risk_register: list[AssumptionRiskPayload]
    flags: list[FlagPayload]
    verdict: VerdictPayload
    confidence: Confidence
    unverified: list[str] = Field(default_factory=list)
    thesis: str | None = None
