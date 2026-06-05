"""LLM client factory + model-alias resolution.

Single seam for picking Anthropic direct API vs AWS Bedrock. The runner
and the categorizer both go through here, so swapping providers is one
env var (`LLM_PROVIDER`) with no code changes.

Bedrock uses inference-profile ids that don't match the friendly names
agent specs use (e.g. `claude-sonnet-4-6`). The alias map translates at
call time. Built-in defaults cover the current Claude 4.x family; user
overrides via `BEDROCK_MODEL_ALIASES` (JSON) take precedence."""
from __future__ import annotations

import json
import logging
from typing import Any

from ..config import settings


log = logging.getLogger(__name__)


# Best-effort defaults — confirm these against your Bedrock account before
# production. Override per-model via BEDROCK_MODEL_ALIASES (JSON env).
# `us.` prefix = cross-region inference profile (recommended for v4.x).
BEDROCK_DEFAULTS: dict[str, str] = {
    "claude-haiku-4-5-20251001": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "claude-sonnet-4-6": "us.anthropic.claude-sonnet-4-6-20251029-v1:0",
    "claude-opus-4-8": "us.anthropic.claude-opus-4-8-20251029-v1:0",
}


_async_client: Any = None
_warned_unmapped: set[str] = set()


def _parse_overrides() -> dict[str, str]:
    raw = (settings.bedrock_model_aliases or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            log.warning("BEDROCK_MODEL_ALIASES must be a JSON object")
            return {}
        return {str(k): str(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        log.warning("BEDROCK_MODEL_ALIASES is not valid JSON: %s", e)
        return {}


def resolve_model(model_id: str) -> str:
    """Translate a friendly model id to the provider-native id.

    On anthropic (direct API), returns the input unchanged.
    On bedrock, looks up the alias map (overrides + defaults); falls
    through to the input id if no alias is set (so the user sees a
    clean Bedrock 'model not found' error instead of silently calling
    the wrong model)."""
    if (settings.llm_provider or "anthropic").lower() != "bedrock":
        return model_id
    overrides = _parse_overrides()
    aliases = {**BEDROCK_DEFAULTS, **overrides}
    if model_id in aliases:
        return aliases[model_id]
    if model_id not in _warned_unmapped:
        log.warning(
            "no Bedrock alias for %r — pass through; set BEDROCK_MODEL_ALIASES "
            "to map it to your account's inference-profile id.",
            model_id,
        )
        _warned_unmapped.add(model_id)
    return model_id


def get_async_client() -> Any:
    """Process-wide async LLM client. Both SDK constructors are lazy-imported
    so importing this module doesn't drag in the wrong deps."""
    global _async_client
    if _async_client is None:
        provider = (settings.llm_provider or "anthropic").lower()
        if provider == "bedrock":
            from anthropic import AsyncAnthropicBedrock  # type: ignore[import-not-found]

            _async_client = AsyncAnthropicBedrock(
                aws_region=settings.aws_bedrock_region,
            )
            log.info("LLM provider: bedrock (region=%s)", settings.aws_bedrock_region)
        elif provider == "anthropic":
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

            _async_client = AsyncAnthropic()
            log.info("LLM provider: anthropic (direct API)")
        else:
            raise ValueError(
                f"unknown llm_provider: {provider!r} "
                "(expected 'anthropic' or 'bedrock')"
            )
    return _async_client


def set_async_client(client: Any | None) -> None:
    """Install (or clear) the cached client. Used by tests + smokes."""
    global _async_client
    _async_client = client
