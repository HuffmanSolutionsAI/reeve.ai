from .capability import Tier
from .scope import (
    KNOWN_GATED_ACTIONS,
    KNOWN_INTERNAL_ACTIONS,
    KNOWN_READ_SCOPES,
    SENSITIVE_READS,
    check_scope,
)
from .spec import AgentSpec, RunContext, RunResult
from .tool import REGISTRY, Tool, tool

# Register every built-in tool via decorator side effects. Must precede the
# loader, which validates `spec.tools` against REGISTRY.
from . import tools  # noqa: F401,E402

from .loader import DEFAULT_MODEL, SpecError, list_agents, load_agent  # noqa: E402
from .proposals import ExecutionError, execute_approved_proposal  # noqa: E402
from .runner import MAX_TURNS, run_agent  # noqa: E402

__all__ = [
    "AgentSpec",
    "DEFAULT_MODEL",
    "ExecutionError",
    "KNOWN_GATED_ACTIONS",
    "KNOWN_INTERNAL_ACTIONS",
    "KNOWN_READ_SCOPES",
    "MAX_TURNS",
    "REGISTRY",
    "RunContext",
    "RunResult",
    "SENSITIVE_READS",
    "SpecError",
    "Tier",
    "Tool",
    "check_scope",
    "execute_approved_proposal",
    "list_agents",
    "load_agent",
    "run_agent",
    "tool",
]
