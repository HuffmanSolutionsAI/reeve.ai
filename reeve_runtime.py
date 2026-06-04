"""
Reeve — agent runtime (vertical slice: runtime + Reeve + Ana).

An agent is a SPEC plugged into this runtime. The runtime owns the LLM loop,
tool dispatch, capability enforcement, audit, and the proposal/approval path.
Agents differ only in: system prompt, allowed tools, read scope, output contract.

SAFETY CORE: capability tiers are enforced HERE, not in the prompt.
  READ / ACT_INTERNAL  -> handler runs inline.
  ACT_GATED            -> handler is NEVER called from the agent loop. The runtime
                          emits a Proposal and returns "awaiting approval". The real
                          handler runs only via execute_approved_proposal(), which
                          the agent cannot reach. Agents hold no credentials.

Stack notes: FastAPI entrypoint; swap the in-memory stores for DynamoDB (audit,
append-only) + Mongo/Dynamo (portfolio, pipeline). Long multi-tool runs may exceed
a Lambda timeout — run the agent loop on Step Functions / a longer-lived worker.
"""
from __future__ import annotations
import enum, json, uuid, datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Any
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = "claude-sonnet-4-6"   # default; use "claude-opus-4-8" for the hardest underwriting reasoning
MAX_TURNS = 8                 # tool-use loop guard


# ---------------------------------------------------------------- capability model
class Tier(enum.Enum):
    READ = "read"                 # see scoped data
    ACT_INTERNAL = "act_internal" # reversible, no money/legal/tenant — runs unattended
    ACT_GATED = "act_gated"       # spends money / creates obligation / contacts a tenant — proposal only


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict           # JSON schema for the model
    tier: Tier
    handler: Callable[..., Any]  # for ACT_GATED, only ever called by the execution layer
    terminal: bool = False       # if True, calling it ends the agent run (emits the output contract)

    def anthropic_schema(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


REGISTRY: dict[str, Tool] = {}

def tool(name, tier, schema, description, terminal=False):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, schema, tier, fn, terminal)
        return fn
    return deco


# ---------------------------------------------------------------- audit (append-only)
@dataclass
class AuditEvent:
    actor: str; kind: str; detail: dict
    ts: str = field(default_factory=lambda: dt.datetime.utcnow().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

class AuditLog:
    """Immutable in prod (DynamoDB, no update/delete). This is the Activity surface."""
    def __init__(self): self._events: list[AuditEvent] = []
    def write(self, actor, kind, detail): self._events.append(AuditEvent(actor, kind, detail))
    def feed(self): return list(self._events)

AUDIT = AuditLog()


# ---------------------------------------------------------------- proposals (gated path)
@dataclass
class Proposal:
    agent: str; action: str; payload: dict; summary: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = "pending"   # pending -> approved/rejected -> executed

def execute_approved_proposal(p: Proposal):
    """Run by the EXECUTION LAYER after a human approves — NOT reachable from an agent.
    This is where credentials live. Deferred until agent #4 (Cole)."""
    assert p.status == "approved"
    REGISTRY[p.action].handler(**p.payload)   # the only place a gated handler ever runs
    p.status = "executed"
    AUDIT.write("execution_layer", "executed", {"proposal": p.id, "action": p.action})


# ---------------------------------------------------------------- agent spec + runner
@dataclass
class AgentSpec:
    id: str; name: str; desk: str
    system_prompt: str
    tool_names: list[str]        # the ONLY tools this agent may call (least privilege)
    context_loader: Callable[[dict], str] = lambda ctx: ""  # injects portfolio/buy-box, logs the read

@dataclass
class RunResult:
    agent: str
    artifact: dict | None = None          # the output contract (e.g. deal_analysis)
    text: str = ""
    proposals: list[Proposal] = field(default_factory=list)


def run_agent(spec: AgentSpec, task: str, ctx: dict) -> RunResult:
    tools = [REGISTRY[n] for n in spec.tool_names]
    schemas = [t.anthropic_schema() for t in tools]
    system = spec.system_prompt + "\n\n" + spec.context_loader(ctx)
    messages = [{"role": "user", "content": task}]
    out = RunResult(agent=spec.id)

    for _ in range(MAX_TURNS):
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=system,
                                      messages=messages, tools=schemas)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        out.text = "".join(b.text for b in resp.content if b.type == "text") or out.text
        if not tool_uses:
            break

        results = []
        for tu in tool_uses:
            # enforcement: the model can only have been given spec tools, but verify anyway
            if tu.name not in spec.tool_names:
                AUDIT.write(spec.id, "blocked_tool", {"tool": tu.name})
                results.append(_tr(tu.id, "ERROR: tool not permitted for this agent.", True)); continue

            t = REGISTRY[tu.name]
            if t.tier is Tier.ACT_GATED:
                # GATE: never execute. Emit a proposal; the model is told it must wait.
                p = Proposal(spec.id, t.name, dict(tu.input), summary=str(tu.input))
                out.proposals.append(p)
                AUDIT.write(spec.id, "proposed", {"action": t.name, "proposal": p.id})
                results.append(_tr(tu.id, "PROPOSED — requires the investor's sign-off; not executed."))
                continue

            # READ / ACT_INTERNAL: run inline, audit it
            try:
                value = t.handler(**tu.input)
                AUDIT.write(spec.id, t.tier.value, {"tool": t.name})
            except Exception as e:
                results.append(_tr(tu.id, f"ERROR: {e}", True)); continue

            if t.terminal:                       # output contract emitted -> end run
                out.artifact = value
                AUDIT.write(spec.id, "artifact", {"type": value.get("type")})
                return out
            results.append(_tr(tu.id, json.dumps(value)))

        messages.append({"role": "user", "content": results})
    return out

def _tr(tool_use_id, text, is_error=False):
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": text, "is_error": is_error}


# ---------------------------------------------------------------- tools (STUBS — wire to your systems)
@tool("get_buy_box", Tier.READ, {"type": "object", "properties": {}},
      "Return the investor's buy-box and return thresholds.")
def get_buy_box():
    return {"cap_floor": 0.07, "min_dscr": 1.20, "target_coc": 0.08}  # TODO: portfolio store

@tool("property_analysis", Tier.READ,
      {"type": "object", "properties": {"address": {"type": "string"}, "ask": {"type": "number"}},
       "required": ["address"]},
      "Run the underwriting model on a property. (Your existing analysis tool.)")
def property_analysis(address, ask=None):
    return {"address": address, "ask": ask, "cap_in_place": 0.054, "dscr": 1.24, "...": "TODO: real tool"}

@tool("pull_comps", Tier.READ,
      {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
      "Pull rent and sales comps for the area.")
def pull_comps(address):
    return {"avg_market_rent": 1466, "...": "TODO: comps source"}

@tool("query_sourcing_pipeline", Tier.READ,
      {"type": "object", "properties": {"filter": {"type": "string"}}},
      "Query the DuckDB/Parquet distressed-property pipeline.")
def query_sourcing_pipeline(filter=""):
    return {"candidates": [], "...": "TODO: DuckDB"}

@tool("submit_deal_analysis", Tier.ACT_INTERNAL,
      {"type": "object", "properties": {"artifact": {"type": "object"}}, "required": ["artifact"]},
      "Emit the final deal_analysis artifact and save the deal to the pipeline. Call this to finish.",
      terminal=True)
def submit_deal_analysis(artifact):
    # TODO: validate against the deal_analysis schema; persist pipeline status (analyzed/pursue/pass)
    artifact["type"] = "deal_analysis"
    return artifact

# --- example of a GATED tool (Cole, later). Defined to show the pattern; not in any v1 spec.
@tool("send_loi", Tier.ACT_GATED,
      {"type": "object", "properties": {"address": {"type": "string"}, "price": {"type": "number"}},
       "required": ["address", "price"]},
      "Send a letter of intent. GATED — emits a proposal; never executes from the agent.")
def send_loi(address, price):
    ...  # real send lives here, reachable ONLY via execute_approved_proposal()


# ---------------------------------------------------------------- specs
ANA = AgentSpec(
    id="ana", name="Ana", desk="Acquisition",
    system_prompt=(  # pull the full prompt from reeve_agent_specs.md §4
        "You are Ana, the underwriter. Given a property, produce a rigorous, honest analysis "
        "and a verdict: pursue or pass, and at what price. Underwrite to the buy-box; compare "
        "to thresholds explicitly. Show every assumption. Distinguish in-place from pro-forma. "
        "Flag anything unverified and lower confidence. You are read-only: never make an offer. "
        "Finish by calling submit_deal_analysis with the full artifact."),
    tool_names=["get_buy_box", "property_analysis", "pull_comps",
                "query_sourcing_pipeline", "submit_deal_analysis"],
)

# Reeve dispatches to specialists. dispatch() runs a specialist and returns its artifact.
SPECIALISTS = {"ana": ANA}

@tool("dispatch", Tier.ACT_INTERNAL,
      {"type": "object",
       "properties": {"agent_id": {"type": "string"}, "task": {"type": "string"}},
       "required": ["agent_id", "task"]},
      "Route a task to a specialist and return their result.")
def dispatch(agent_id, task, _ctx=None):
    sub = run_agent(SPECIALISTS[agent_id], task, _ctx or {})
    return {"agent": agent_id, "artifact": sub.artifact, "text": sub.text}

REEVE = AgentSpec(
    id="reeve", name="Reeve", desk="orchestrator",
    system_prompt=(  # full prompt in reeve_agent_specs.md §3
        "You are Reeve, chief of staff. Triage every inbound and route it to the right "
        "specialist via dispatch(). Lead with the answer, numbers first; name the specialist "
        "you bring in. You never execute gated actions — you present proposals for sign-off. "
        "Assemble one coherent reply; never make the investor stitch desks together."),
    tool_names=["dispatch"],
)


# ---------------------------------------------------------------- FastAPI entrypoint
from fastapi import FastAPI
from pydantic import BaseModel
app = FastAPI()

class Inbound(BaseModel):
    message: str
    investor_id: str

@app.post("/chat")
def chat(inb: Inbound):
    ctx = {"investor_id": inb.investor_id}  # TODO: load portfolio/preferences, scope reads
    # NOTE: dispatch needs ctx; in real code thread ctx through (closure/partial) rather than a default arg.
    result = run_agent(REEVE, inb.message, ctx)
    return {
        "speaker": "Reeve",
        "text": result.text,
        "artifacts": [result.artifact] if result.artifact else [],
        "proposals": [p.__dict__ for p in result.proposals],   # empty in v1 (Ana is read-only)
        "activity": [e.__dict__ for e in AUDIT.feed()],
    }
