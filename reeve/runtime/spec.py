from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentSpec:
    """Parsed from `agents/<id>.md`. The runtime trusts the spec; the loader
    enforces that every tool/scope is known and that tool.reads/writes are a
    subset of the agent's read_scope/internal_actions/gated_actions."""

    id: str
    name: str
    desk: str
    model: str
    system_prompt: str
    tool_names: list[str]
    read_scope: list[str] = field(default_factory=list)
    internal_actions: list[str] = field(default_factory=list)
    gated_actions: list[str] = field(default_factory=list)
    output_contract: str | None = None
    terminal_tool: str | None = None


@dataclass
class RunContext:
    """Carried through every tool invocation. Tools opt in to receiving this
    via `needs_ctx=True` on the @tool decorator."""

    investor_id: str
    agent_id: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None


@dataclass
class RunResult:
    agent: str
    artifact: dict | None = None
    text: str = ""
    proposal_ids: list[str] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | low_confidence | failed | missing_data | gated
