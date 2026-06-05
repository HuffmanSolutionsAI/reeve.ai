"""Rule-based transaction categorizer.

Replaceable with an ML categorizer when Bea ships — the function signature
stays the same. Categories are the ones the morning brief and cash-flow
report aggregate over."""
from __future__ import annotations

import re


# Ordered: first match wins. Patterns lowered before matching.
CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    ("rent", re.compile(r"\brent\b|tenant payment|lease payment", re.I)),
    ("debt_service", re.compile(r"mortgage|loan payment|principal|interest payment", re.I)),
    ("taxes", re.compile(r"property tax|\btax(es)?\b", re.I)),
    ("insurance", re.compile(r"insur", re.I)),
    ("management", re.compile(r"property mgmt|management fee|\bmgmt\b", re.I)),
    ("utilities", re.compile(r"water|sewer|gas company|electric utility|utility", re.I)),
    ("maintenance", re.compile(r"plumb|hvac|electric(al)? repair|repair|maintenance|handyman|paint", re.I)),
    ("supplies", re.compile(r"home depot|lowe'?s|supplies|materials|hardware", re.I)),
    ("legal", re.compile(r"attorney|legal|filing fee", re.I)),
    ("capex", re.compile(r"roof|hvac replacement|appliance|capex", re.I)),
]


def categorize(description: str, *, plaid_categories: list[str] | None = None) -> str:
    """Pick the first matching category for `description` (free text) and the
    Plaid taxonomy hints. Returns 'other' if nothing matches — never raises."""
    text = " ".join([description, *(plaid_categories or [])])
    for label, pattern in CATEGORIES:
        if pattern.search(text):
            return label
    return "other"
