"""LLM-backed categorizer.

Used as a fallback for descriptions the rule-based pass labels `other`.
Results are cached by description hash (lowercased, whitespace-collapsed)
so we don't re-bill the API for repeat descriptions across a sync.

The LLM client is injectable so tests can swap in a deterministic
stand-in without an API key. The default lazy-loads AsyncAnthropic."""
from __future__ import annotations

import hashlib
import re
from typing import Any


# The label set MUST match `reeve.finance.categorizer.CATEGORIES` order;
# the LLM is constrained to pick from these.
CATEGORY_LABELS: list[str] = [
    "rent", "debt_service", "taxes", "insurance", "management",
    "utilities", "maintenance", "supplies", "legal", "capex", "other",
]


_PROMPT = """You are a real-estate bookkeeping categorizer.

Pick exactly one label that best matches the transaction description.
Allowed labels (and what they mean):
- rent              — tenant rent payment received
- debt_service      — mortgage / loan payment
- taxes             — property tax payment
- insurance         — property insurance premium
- management        — property management fee
- utilities         — water, sewer, gas, electric, etc.
- maintenance       — repairs, service calls, handyman, cleaning
- supplies          — materials, hardware-store purchases
- legal             — attorney fees, filing fees
- capex             — capital improvements (roof, HVAC replacement)
- other             — none of the above

Reply with the label only — a single word, lowercase, no punctuation.

Description: {description}"""


class LLMCategorizer:
    """Async + cached. Use `categorize(description)` from anywhere; tests
    pass `llm=<mock>` to bypass the real Anthropic client."""

    def __init__(self, *, llm: Any = None, model: str = "claude-haiku-4-5-20251001") -> None:
        self._llm = llm
        self._model = model
        self._cache: dict[str, str] = {}

    @staticmethod
    def _key(description: str) -> str:
        norm = re.sub(r"\s+", " ", description.strip().lower())
        return hashlib.sha1(norm.encode()).hexdigest()

    async def categorize(self, description: str) -> str:
        key = self._key(description)
        if key in self._cache:
            return self._cache[key]
        client = await self._client()
        prompt = _PROMPT.format(description=description.strip())
        resp = await client.messages.create(
            model=self._model,
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
        raw = "".join(text_parts).strip().lower()
        # Take the first non-empty token, strip surrounding punctuation.
        token = next(
            (t.strip(".,'\"`*-:") for t in raw.split() if t.strip(".,'\"`*-:")),
            "other",
        )
        label = token if token in CATEGORY_LABELS else "other"
        self._cache[key] = label
        return label

    async def _client(self) -> Any:
        if self._llm is None:
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

            self._llm = AsyncAnthropic()
        return self._llm


# ---- module-level singleton + injection point for tests --------------------
_singleton: LLMCategorizer | None = None


def get_default() -> LLMCategorizer:
    global _singleton
    if _singleton is None:
        _singleton = LLMCategorizer()
    return _singleton


def set_default(categorizer: LLMCategorizer | None) -> None:
    """Install a process-wide categorizer (used by tests + dev fixtures)."""
    global _singleton
    _singleton = categorizer
