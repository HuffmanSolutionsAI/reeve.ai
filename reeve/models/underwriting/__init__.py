"""Value-add / distressed multifamily underwriting models.

Subpackage of `reeve.models`. Imported by the v2 engine
(`reeve.underwriting.value_add`) and the value_add_analysis contract.

The v1 stabilized models (`reeve.models.deal`, etc.) are unchanged and
still drive `profile=stabilized` deals."""
from .assumptions import (
    AncillaryItem,
    AncillaryKind,
    BrokerProforma,
    DealAssumptions,
    RequiredMargin,
    RequiredMarginType,
    TargetRent,
)
from .common import DealProfile
from .financing import (
    BridgeFinancing,
    FinancingScenario,
    OccupancyGate,
    PermFinancing,
    SponsorRequirements,
)
from .market_context import CapRates, CompCondition, MarketContext, RentComp
from .operating_statement import (
    InsuranceQuoteSource,
    InsuranceRecord,
    OpExCategory,
    OperatingLine,
    OperatingPeriod,
    OperatingStatement,
    TaxReassessmentMethod,
    TaxRecord,
    UtilityRecord,
)
from .property_profile import (
    CompletedCapital,
    ConditionInventory,
    PropertyProfile,
    Site,
    Structure,
    StructureType,
    UnitMix,
)
from .provenance import Provenance, Sourced, is_assumed, is_broker_claimed, is_verified
from .renovation_budget import (
    CONTINGENCY_BUMP_PRE_1980,
    CONTINGENCY_BUMP_UNTESTED_SYSTEMS,
    CONTINGENCY_FLOOR_BASE,
    AbatementAllowance,
    BudgetTier,
    RenovationBudget,
    SystemItem,
    SystemLine,
    SystemStatus,
)
from .rent_roll import (
    AchievedRenovatedStats,
    ConditionTier,
    IngestFormat,
    LeaseRow,
    RentRoll,
    RentRollDerived,
    RentRollSource,
    RentRollValidation,
    ValidationCheck,
    recompute_derived,
)

__all__ = [
    "AbatementAllowance",
    "AchievedRenovatedStats",
    "AncillaryItem",
    "AncillaryKind",
    "BridgeFinancing",
    "BrokerProforma",
    "BudgetTier",
    "CONTINGENCY_BUMP_PRE_1980",
    "CONTINGENCY_BUMP_UNTESTED_SYSTEMS",
    "CONTINGENCY_FLOOR_BASE",
    "CapRates",
    "CompCondition",
    "CompletedCapital",
    "ConditionInventory",
    "ConditionTier",
    "DealAssumptions",
    "DealProfile",
    "FinancingScenario",
    "IngestFormat",
    "InsuranceQuoteSource",
    "InsuranceRecord",
    "LeaseRow",
    "MarketContext",
    "OccupancyGate",
    "OpExCategory",
    "OperatingLine",
    "OperatingPeriod",
    "OperatingStatement",
    "PermFinancing",
    "PropertyProfile",
    "Provenance",
    "RenovationBudget",
    "RentComp",
    "RentRoll",
    "RentRollDerived",
    "RentRollSource",
    "RentRollValidation",
    "RequiredMargin",
    "RequiredMarginType",
    "Site",
    "Sourced",
    "SponsorRequirements",
    "Structure",
    "StructureType",
    "SystemItem",
    "SystemLine",
    "SystemStatus",
    "TargetRent",
    "TaxReassessmentMethod",
    "TaxRecord",
    "UnitMix",
    "UtilityRecord",
    "ValidationCheck",
    "is_assumed",
    "is_broker_claimed",
    "is_verified",
    "recompute_derived",
]
