"""Rule-based transaction categorizer + LLM cascade.

`categorize(description, …)` is the rule-only pass (sync, no IO, no
API). `categorize_async(description, …)` honors `settings.categorizer`:
  - 'rules'   — rule-only (no LLM call).
  - 'cascade' — rules first; for 'other' results, fall back to the LLM
    categorizer (cached by description hash).

Bea's existing tools use the sync `categorize` directly; the Plaid sync
path uses `categorize_async` so a new ingest passes through whichever
strategy the env says."""
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


async def categorize_async(
    description: str, *, plaid_categories: list[str] | None = None,
) -> str:
    """Cascade categorizer honoring `settings.categorizer`.

    Falls back to the LLM categorizer only when rules return 'other' AND
    the cascade strategy is enabled."""
    from ..config import settings
    label = categorize(description, plaid_categories=plaid_categories)
    if label != "other":
        return label
    if (settings.categorizer or "rules").lower() != "cascade":
        return label
    from .llm_categorizer import get_default
    try:
        return await get_default().categorize(description)
    except Exception:
        # Any LLM failure is non-fatal — keep the rule-based 'other'.
        return label
