"""The agent loop: LLM tool-use with §5 access enforcement and SSE-friendly
event emission.

Enforcement layers (unchanged from step 2):
  1. Tool whitelist — only `spec.tool_names` are exposed to the model.
  2. Scope check — `tool.reads` ⊆ `spec.read_scope` and `tool.writes` ⊆ the
     matching action set. Loader catches most at parse time; this re-checks
     at call time (defense in depth).
  3. Sensitive-read audit — every read with a scope in `SENSITIVE_READS`
     emits a `read` event before the handler runs.
  4. Gated tier — `ACT_GATED` handlers are NEVER called from this loop. The
     runtime persists a Proposal, emits `proposed`, and returns a textual
     'PROPOSED' tool result.

New in step 4: events flow through `ctx.event_sink` as the agent works.
Event types: `routing`, `handoff`, `tool`, `artifact`, `message`. Dispatch
propagates the sink to sub-agents so their events surface on the parent
SSE stream."""
from __future__ import annotations

import inspect
import json
from dataclasses import replace
from typing import Any

from ..audit import AuditKind, EntityType, get_audit
from ..models.agent_run import AgentRunStatus
from ..proposals import get_client as get_proposals_client
from ..repos.agent_runs import finish_run, start_run
from .capability import Tier
from .context import default_context_loader
from .scope import SENSITIVE_READS, check_scope
from .spec import AgentSpec, RunContext, RunResult
from .tool import REGISTRY, Tool


MAX_TURNS = 8

_client_singleton: Any = None


def _anthropic() -> Any:
    global _client_singleton
    if _client_singleton is None:
        from anthropic import AsyncAnthropic  # type: ignore[import-not-found]

        _client_singleton = AsyncAnthropic()
    return _client_singleton


def _tool_result(tool_use_id: str, content: str, is_error: bool = False) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


async def _call_handler(t: Tool, kwargs: dict) -> Any:
    if inspect.iscoroutinefunction(t.handler):
        return await t.handler(**kwargs)
    return t.handler(**kwargs)


async def _emit(ctx: RunContext, event: str, **data: Any) -> None:
    if ctx.event_sink is not None:
        await ctx.event_sink({"event": event, **data})


async def run_agent(
    spec: AgentSpec,
    task: str,
    ctx: RunContext,
    *,
    llm: Any = None,
) -> RunResult:
    llm = llm or _anthropic()
    audit = get_audit()

    sub_ctx = replace(ctx, agent_id=spec.id)
    run = await start_run(
        conversation_id=ctx.conversation_id, agent=spec.id, task=task
    )
    sub_ctx = replace(sub_ctx, agent_run_id=run.id)

    await _emit(ctx, "routing", agent=spec.id, name=spec.name, desk=spec.desk)

    runtime_context = await default_context_loader(sub_ctx)
    system_prompt = spec.system_prompt + ("\n\n" + runtime_context if runtime_context else "")

    tools = [REGISTRY[n] for n in spec.tool_names]
    schemas = [t.anthropic_schema() for t in tools]
    messages: list[dict] = [{"role": "user", "content": task}]
    out = RunResult(agent=spec.id)

    artifact_id: str | None = None
    run_status = AgentRunStatus.OK
    terminated = False

    for _turn in range(MAX_TURNS):
        resp = await llm.messages.create(
            model=spec.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=schemas,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        text_parts = [b.text for b in resp.content if b.type == "text"]
        if text_parts:
            out.text = "".join(text_parts)
        if not tool_uses:
            break

        results: list[dict] = []
        for tu in tool_uses:
            # 1) whitelist
            if tu.name not in spec.tool_names:
                audit.emit(
                    investor_id=ctx.investor_id, actor=spec.id,
                    kind=AuditKind.BLOCKED,
                    detail={"tool": tu.name, "reason": "not_in_spec"},
                )
                results.append(_tool_result(tu.id, "ERROR: tool not permitted.", True))
                continue

            t = REGISTRY[tu.name]

            # 2) scope check (defense-in-depth)
            violation = check_scope(spec, t)
            if violation is not None:
                audit.emit(
                    investor_id=ctx.investor_id, actor=spec.id,
                    kind=AuditKind.BLOCKED,
                    detail={"tool": tu.name, "reason": violation},
                )
                results.append(_tool_result(tu.id, f"ERROR: {violation}", True))
                continue

            # 3) sensitive-read audit
            for r in t.reads:
                if r in SENSITIVE_READS:
                    audit.emit(
                        investor_id=ctx.investor_id, actor=spec.id,
                        kind=AuditKind.READ,
                        detail={"tool": tu.name, "scope": r},
                    )

            # SSE event before the call so the UI can show the working indicator.
            # Dispatch emits its own `handoff` event from inside the tool; suppress
            # the generic `tool` for dispatch to keep the stream clean.
            if t.name != "dispatch":
                await _emit(ctx, "tool", agent=spec.id, tool=t.name)

            # 4) ACT_GATED → proposal, never executed from this loop
            if t.tier is Tier.ACT_GATED:
                proposal_payload = dict(tu.input)
                proposal = await get_proposals_client().write(
                    investor_id=ctx.investor_id, agent=spec.id,
                    action=t.name, payload=proposal_payload,
                    summary=f"{spec.name}: {t.description}",
                )
                out.proposal_ids.append(proposal.id)
                audit.emit(
                    investor_id=ctx.investor_id, actor=spec.id,
                    kind=AuditKind.PROPOSED,
                    entity_type=EntityType.PROPOSAL, entity_id=proposal.id,
                    detail={"action": t.name},
                )
                await _emit(
                    ctx, "proposal", agent=spec.id,
                    proposal_id=proposal.id, action=t.name,
                    payload=proposal_payload,
                    summary=f"{spec.name}: {t.description}",
                )
                results.append(_tool_result(
                    tu.id,
                    "PROPOSED — requires the investor's sign-off; not executed.",
                ))
                continue

            # READ / ACT_INTERNAL: run inline
            kwargs = dict(tu.input)
            if t.needs_ctx:
                kwargs["_ctx"] = sub_ctx
            try:
                value = await _call_handler(t, kwargs)
                out.tools_called.append(t.name)
                audit.emit(
                    investor_id=ctx.investor_id, actor=spec.id,
                    kind=(
                        AuditKind.READ if t.tier is Tier.READ
                        else AuditKind.ACT_INTERNAL
                    ),
                    detail={"tool": t.name},
                )
            except Exception as e:
                run_status = AgentRunStatus.FAILED
                results.append(_tool_result(tu.id, f"ERROR: {e}", True))
                continue

            if t.terminal:
                out.artifact = value if isinstance(value, dict) else None
                if isinstance(value, dict):
                    artifact_id = value.get("artifact_id")
                    audit.emit(
                        investor_id=ctx.investor_id, actor=spec.id,
                        kind=AuditKind.ARTIFACT,
                        entity_type=EntityType.ARTIFACT, entity_id=artifact_id,
                        detail={"type": value.get("type")},
                    )
                    await _emit(
                        ctx, "artifact", agent=spec.id,
                        artifact_id=artifact_id, type=value.get("type"),
                        payload=value,
                    )
                terminated = True
                break
            results.append(_tool_result(tu.id, json.dumps(value, default=str)))

        if terminated:
            break
        messages.append({"role": "user", "content": results})

    if out.proposal_ids and out.artifact is None:
        out.status = "gated"
    elif run_status is AgentRunStatus.FAILED:
        out.status = "failed"
    else:
        out.status = "ok"

    if out.text:
        await _emit(ctx, "message", agent=spec.id, name=spec.name, text=out.text)

    await finish_run(
        run.id,
        status=run_status,
        artifact_id=artifact_id,
        tools_called=out.tools_called,
        proposal_ids=out.proposal_ids,
    )
    return out
