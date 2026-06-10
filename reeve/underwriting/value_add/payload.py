"""Serialize an AnalysisResult to a value_add_analysis payload dict.

Kept separate from the engine so the engine doesn't pull in Pydantic.
Used by the submit_value_add_analysis tool to write the artifact."""
from __future__ import annotations

from dataclasses import asdict

from .runner import AnalysisResult


def _noi_dict(noi) -> dict:
    return {
        "state": noi.state,
        "gross_potential_income": noi.gross_potential_income,
        "vacancy_loss": noi.vacancy_loss,
        "credit_loss": noi.credit_loss,
        "concession_loss": noi.concession_loss,
        "other_income": noi.other_income,
        "effective_gross_income": noi.effective_gross_income,
        "opex_lines": dict(noi.opex_lines),
        "opex_total": noi.opex_total,
        "noi": noi.noi,
        "reserves": noi.reserves,
    }


def result_to_payload(
    result: AnalysisResult,
    *,
    deal_id: str,
    address: str,
    units: int,
    as_of: str | None = None,
    thesis: str | None = None,
) -> dict:
    """Render the engine result into the value_add_analysis wire shape."""
    return {
        "type": "value_add_analysis",
        "deal_id": deal_id,
        "address": address,
        "units": units,
        "as_of": as_of,
        "noi_panel": {
            "in_place": _noi_dict(result.noi_in_place),
            "stabilized": _noi_dict(result.noi_stabilized),
            "stabilized_plus_ancillary": _noi_dict(result.noi_stabilized_plus_ancillary),
            "broker_proforma_diff": [
                {"line": d.line, "broker": d.broker, "engine": d.engine, "delta": d.delta}
                for d in result.broker_diff
            ],
        },
        "valuation_panel": {
            "floor_value": result.band.floor_value,
            "stabilized_value": result.band.stabilized_value,
            "cost_to_stabilize": result.band.cost_to_stabilize,
            "required_margin_dollars": result.band.required_margin_dollars,
            "ceiling_max_offer": result.band.ceiling_max_offer,
            "bid_ladder": {
                "opening": result.band.opening,
                "target_bid": result.band.target_bid,
                "walk_away": result.band.walk_away,
            },
        },
        "sources_and_uses": {
            "bridge_basis": result.financing.bridge_basis,
            "bridge_proceeds": result.financing.bridge_proceeds,
            "bridge_equity_in": result.financing.bridge_equity_in,
            "bridge_annual_interest": result.financing.bridge_annual_interest,
            "perm_by_ltv": result.financing.perm_by_ltv,
            "perm_by_dscr": result.financing.perm_by_dscr,
            "perm_loan": result.financing.perm_loan,
            "perm_annual_ds": result.financing.perm_annual_ds,
            "refi_costs": result.financing.refi_costs,
            "refi_proceeds_net": result.financing.refi_proceeds_net,
            "equity_recapture": result.financing.equity_recapture,
            "residual_equity": result.financing.residual_equity,
            "structure": result.financing.structure,
            "perm_first_qualifies": result.financing.perm_first_qualifies,
            "occupancy_gate_pct": result.financing.occupancy_gate_pct,
        },
        "returns": {
            "stabilized_cash_on_cash": result.financing.stabilized_cash_on_cash,
            "perm_dscr_at_stabilized": result.financing.perm_dscr_at_stabilized,
        },
        "cross_checks": [
            {"name": c.name, "value": c.value, "status": c.status, "detail": c.detail}
            for c in result.cross_checks
        ],
        "sensitivity": {
            "swing": result.sensitivity_swing,
            "cells": [asdict(c) for c in result.sensitivity_cells],
        },
        "risk_register": [
            {
                "input": r.input,
                "provenance": r.provenance,
                "value_used": r.value_used,
                "perturbation_pct": r.perturbation_pct,
                "max_offer_low": r.max_offer_low,
                "max_offer_high": r.max_offer_high,
                "swing_dollars": r.swing_dollars,
                "verification_action": r.verification_action,
            }
            for r in result.risk_register
        ],
        "flags": [
            {"code": f.code, "severity": f.severity, "text": f.text, "unblock_action": f.unblock_action}
            for f in result.flags
        ],
        "verdict": {
            "decision": result.decision,
            "max_price": result.max_price,
            "headline": result.headline,
        },
        "confidence": result.confidence,
        "thesis": thesis,
    }
