"""Financing — two-phase, gated by occupancy.

The Freddie SBL 90/90 (90% physical for 90 days) rule is encoded as data,
not prose. `OccupancyGate.met_by(physical_occupancy)` returns True when
the property qualifies for the perm program; the engine raises a
blocking `below_agency_gate` flag and forces a bridge-to-perm path
otherwise."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OccupancyGate(BaseModel):
    """Lender occupancy gate (e.g. Freddie SBL: 90% for 90 days)."""
    model_config = ConfigDict(extra="forbid")
    occupancy: float = Field(default=0.90, ge=0, le=1)
    days: int = Field(default=90, ge=0)

    def met_by(self, current_occupancy: float) -> bool:
        return current_occupancy >= self.occupancy


class BridgeFinancing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ltc: float = Field(ge=0, le=1, default=0.75)       # loan-to-cost (price + reno)
    rate: float = Field(ge=0)                           # annual decimal
    interest_only: bool = True
    term_months: int = Field(ge=1)
    origination_pts: float = 0.01                       # decimal
    expected_hold_months: int = Field(ge=1)             # drives net carry

    def monthly_io_payment(self, balance: float) -> float:
        return balance * self.rate / 12.0


class PermFinancing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program: str = "freddie_sbl"                        # informational tag
    rate: float = Field(ge=0)
    amort_years: int = Field(default=30, ge=1)
    min_dscr: float = Field(default=1.25, ge=0)
    max_ltv: float = Field(default=0.75, ge=0, le=1)
    occupancy_gate: OccupancyGate = Field(default_factory=OccupancyGate)
    refi_costs_pct: float = 0.02                        # of perm proceeds

    def monthly_debt_constant(self) -> float:
        """P&I per $1 of loan, monthly. Used as the divisor in DSCR sizing."""
        r = self.rate / 12.0
        n = self.amort_years * 12
        if r <= 0:
            return 1.0 / n
        return r / (1.0 - (1.0 + r) ** -n)

    def annual_debt_constant(self) -> float:
        return self.monthly_debt_constant() * 12


class SponsorRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liquidity_required: float | None = None
    net_worth_required: float | None = None


class FinancingScenario(BaseModel):
    """Embedded on Deal. Multiple scenarios per deal (bridge-to-perm vs
    bank mini-perm vs all-cash) so the engine can compare them."""
    model_config = ConfigDict(extra="forbid")

    label: str
    bridge: BridgeFinancing | None = None
    perm: PermFinancing | None = None
    sponsor: SponsorRequirements = Field(default_factory=SponsorRequirements)

    @property
    def is_bridge_to_perm(self) -> bool:
        return self.bridge is not None and self.perm is not None
