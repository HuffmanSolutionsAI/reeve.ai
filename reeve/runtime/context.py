"""Standing context that every agent's system prompt gets at run time.

Composed into the prompt by `run_agent` as: house body + agent body +
`default_context_loader(ctx)`. Keep it tight — the model pays for every
token, and standing context that exceeds what's relevant becomes noise."""
from __future__ import annotations

from ..repos.investors import get_investor
from .spec import RunContext


async def default_context_loader(ctx: RunContext) -> str:
    if not ctx.investor_id:
        return ""
    investor = await get_investor(ctx.investor_id)
    if investor is None:
        return ""
    bb = investor.buy_box
    lines = ["## Investor context (loaded at run time)"]
    lines.append(f"- Investor: **{investor.name}**" + (f" — {investor.entity_name}" if investor.entity_name else ""))
    parts: list[str] = []
    if bb.cap_floor is not None:
        parts.append(f"cap ≥ {bb.cap_floor * 100:.1f}%")
    if bb.min_dscr is not None:
        parts.append(f"DSCR ≥ {bb.min_dscr:.2f}")
    if bb.target_coc is not None:
        parts.append(f"CoC ≥ {bb.target_coc * 100:.1f}%")
    if parts:
        lines.append(f"- Buy-box: {', '.join(parts)}")
    if bb.markets:
        lines.append(f"- Target markets: {', '.join(bb.markets)}")
    return "\n".join(lines)
