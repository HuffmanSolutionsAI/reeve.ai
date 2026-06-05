from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .capability import Tier


@dataclass
class Tool:
    """A registered capability. `reads`/`writes` are scope labels validated
    against the agent's declared `read_scope`/`internal_actions`/
    `gated_actions` at load time AND at call time (defense in depth)."""

    name: str
    description: str
    input_schema: dict
    tier: Tier
    handler: Callable[..., Any]
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    terminal: bool = False
    needs_ctx: bool = False

    def anthropic_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    tier: Tier,
    input_schema: dict,
    description: str,
    *,
    reads: list[str] | None = None,
    writes: list[str] | None = None,
    terminal: bool = False,
    needs_ctx: bool = False,
):
    """Decorator: register a tool.

    The runtime never calls a gated handler from the agent loop. ACT_GATED
    handlers are reachable ONLY from `execute_approved_proposal`."""

    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            input_schema=input_schema,
            tier=tier,
            handler=fn,
            reads=list(reads or []),
            writes=list(writes or []),
            terminal=terminal,
            needs_ctx=needs_ctx,
        )
        return fn

    return deco
