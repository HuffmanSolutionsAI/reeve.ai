"""Value-add / distressed underwriting engine.

Pure functions over the v2 entity models (`reeve.models.underwriting`).
No IO. Composed by `runner.analyze()` into the value_add_analysis
artifact payload."""
from .costs import StabilizationCosts, cost_to_stabilize
from .cross_checks import CrossCheck, cross_check_panel
from .financing import FinancingSizing, size_financing
from .flags import Flag, detect_flags
from .noi import NOIBreakdown, broker_proforma_diff, in_place_noi, stabilized_noi, stabilized_plus_ancillary_noi
from .risk_register import AssumptionRisk, build_risk_register
from .runner import AnalysisInputs, AnalysisResult, analyze
from .sensitivity import SensitivityCell, sensitivity_grid
from .valuation import ValuationBand, bid_ladder, valuation_band

__all__ = [
    "AnalysisInputs",
    "AnalysisResult",
    "AssumptionRisk",
    "CrossCheck",
    "FinancingSizing",
    "Flag",
    "NOIBreakdown",
    "SensitivityCell",
    "StabilizationCosts",
    "ValuationBand",
    "analyze",
    "bid_ladder",
    "broker_proforma_diff",
    "build_risk_register",
    "cost_to_stabilize",
    "cross_check_panel",
    "detect_flags",
    "in_place_noi",
    "sensitivity_grid",
    "size_financing",
    "stabilized_noi",
    "stabilized_plus_ancillary_noi",
    "valuation_band",
]
