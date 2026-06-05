"""Example ACT_GATED tools — defined to exercise the gate path. None are in
the v1 Ana/Reeve specs; landing the gated agents (Cole first) wires them
into agent frontmatter."""
from __future__ import annotations

from ..capability import Tier
from ..tool import tool


@tool(
    "send_loi",
    Tier.ACT_GATED,
    {
        "type": "object",
        "properties": {
            "address": {"type": "string"},
            "price": {"type": "number"},
        },
        "required": ["address", "price"],
        "additionalProperties": False,
    },
    "Send a letter of intent. GATED — agent emits a proposal; runtime never executes.",
    reads=[],
    writes=["send_loi"],
)
async def send_loi(address: str, price: float) -> dict:
    # Real send lives here. Only `execute_approved_proposal` calls this.
    return {"sent": True, "address": address, "price": price}
