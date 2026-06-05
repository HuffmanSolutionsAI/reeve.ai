"""Markdown frontmatter loader → `AgentSpec`.

Composition: `system_prompt = house.md body + "\\n\\n" + <agent>.md body`.
Validation: every tool listed in frontmatter must be in REGISTRY, and every
scope label must be in `scope.KNOWN_*`. The tool's own `reads`/`writes` must
be a subset of the agent's declared scope. Failures raise SpecError — no
silent-permit fallback."""
from __future__ import annotations

from pathlib import Path

import yaml

from .capability import Tier
from .scope import KNOWN_GATED_ACTIONS, KNOWN_INTERNAL_ACTIONS, KNOWN_READ_SCOPES
from .spec import AgentSpec
from .tool import REGISTRY


DEFAULT_MODEL = "claude-sonnet-4-6"

AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / "agents"


class SpecError(ValueError):
    """A spec file is malformed or references unknown tools/scopes."""


def _parse_md(path: Path) -> tuple[dict, str]:
    if not path.exists():
        raise SpecError(f"{path}: not found")
    text = path.read_text()
    if not text.startswith("---"):
        raise SpecError(f"{path}: missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SpecError(f"{path}: malformed frontmatter")
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n").rstrip()
    if not isinstance(meta, dict):
        raise SpecError(f"{path}: frontmatter must be a YAML mapping")
    return meta, body


def _validate_scope_labels(agent_id: str, meta: dict) -> None:
    for field_name, known in (
        ("read_scope", KNOWN_READ_SCOPES),
        ("internal_actions", KNOWN_INTERNAL_ACTIONS),
        ("gated_actions", KNOWN_GATED_ACTIONS),
    ):
        unknown = set(meta.get(field_name) or []) - known
        if unknown:
            raise SpecError(
                f"{agent_id}.md: unknown {field_name}: {sorted(unknown)}"
            )


def _validate_tools(agent_id: str, meta: dict) -> None:
    tool_names = list(meta.get("tools") or [])
    read_scope = set(meta.get("read_scope") or [])
    internal = set(meta.get("internal_actions") or [])
    gated = set(meta.get("gated_actions") or [])

    for name in tool_names:
        if name not in REGISTRY:
            raise SpecError(f"{agent_id}.md: unknown tool '{name}'")
        t = REGISTRY[name]
        missing_reads = set(t.reads) - read_scope
        if missing_reads:
            raise SpecError(
                f"{agent_id}.md: tool '{name}' reads {sorted(missing_reads)} "
                f"not in read_scope"
            )
        if t.tier is Tier.ACT_INTERNAL:
            missing = set(t.writes) - internal
            if missing:
                raise SpecError(
                    f"{agent_id}.md: ACT_INTERNAL tool '{name}' writes "
                    f"{sorted(missing)} not in internal_actions"
                )
        if t.tier is Tier.ACT_GATED:
            missing = set(t.writes) - gated
            if missing:
                raise SpecError(
                    f"{agent_id}.md: ACT_GATED tool '{name}' writes "
                    f"{sorted(missing)} not in gated_actions"
                )

    terminal = meta.get("terminal_tool")
    if terminal:
        if terminal not in tool_names:
            raise SpecError(
                f"{agent_id}.md: terminal_tool '{terminal}' not in tools"
            )
        if not REGISTRY[terminal].terminal:
            raise SpecError(
                f"{agent_id}.md: tool '{terminal}' is not marked terminal"
            )


def load_agent(agent_id: str, *, agents_dir: Path | None = None) -> AgentSpec:
    base = Path(agents_dir) if agents_dir else AGENTS_DIR
    _, house_body = _parse_md(base / "house.md")
    meta, body = _parse_md(base / f"{agent_id}.md")

    for field_name in ("id", "name", "desk", "tools"):
        if field_name not in meta:
            raise SpecError(f"{agent_id}.md: missing '{field_name}'")
    if meta["id"] != agent_id:
        raise SpecError(
            f"{agent_id}.md: frontmatter id '{meta['id']}' != filename '{agent_id}'"
        )

    _validate_scope_labels(agent_id, meta)
    _validate_tools(agent_id, meta)

    return AgentSpec(
        id=meta["id"],
        name=meta["name"],
        desk=meta["desk"],
        model=meta.get("model") or DEFAULT_MODEL,
        system_prompt=house_body + "\n\n" + body,
        tool_names=list(meta["tools"] or []),
        read_scope=list(meta.get("read_scope") or []),
        internal_actions=list(meta.get("internal_actions") or []),
        gated_actions=list(meta.get("gated_actions") or []),
        output_contract=meta.get("output_contract"),
        terminal_tool=meta.get("terminal_tool"),
    )


def list_agents(*, agents_dir: Path | None = None) -> list[str]:
    base = Path(agents_dir) if agents_dir else AGENTS_DIR
    return sorted(
        p.stem for p in base.glob("*.md") if p.stem != "house"
    )
