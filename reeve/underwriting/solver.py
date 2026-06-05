"""Find the max purchase price that clears the investor's buy-box thresholds."""
from __future__ import annotations

from dataclasses import replace

from .model import UnderwritingInputs, underwrite


def clears(
    inp: UnderwritingInputs,
    *,
    cap_floor: float | None,
    min_dscr: float | None,
    target_coc: float | None = None,
) -> bool:
    """At the given `inp.ask`, does the deal clear every set threshold?"""
    r = underwrite(inp)
    if cap_floor is not None and r.cap_in_place < cap_floor:
        return False
    if min_dscr is not None and r.dscr < min_dscr:
        return False
    if target_coc is not None and r.coc_year1 < target_coc:
        return False
    return True


def max_clearing_price(
    inp: UnderwritingInputs,
    *,
    cap_floor: float | None,
    min_dscr: float | None,
    target_coc: float | None = None,
    lo: float = 1.0,
    hi: float | None = None,
    iters: int = 40,
) -> float | None:
    """Binary search for the highest price at which the deal clears thresholds.

    Returns None if no positive price clears (e.g. NOI ≤ 0 at any price)."""
    high = hi if hi is not None else inp.ask * 2.0
    # As price decreases, cap_in_place rises (NOI is fixed; price shrinks)
    # and DSCR rises (debt service shrinks). So the predicate is monotonic
    # in price — there's a single crossover.
    if not clears(
        replace(inp, ask=lo),
        cap_floor=cap_floor, min_dscr=min_dscr, target_coc=target_coc,
    ):
        return None
    if clears(
        replace(inp, ask=high),
        cap_floor=cap_floor, min_dscr=min_dscr, target_coc=target_coc,
    ):
        return high
    for _ in range(iters):
        mid = (lo + high) / 2
        if clears(
            replace(inp, ask=mid),
            cap_floor=cap_floor, min_dscr=min_dscr, target_coc=target_coc,
        ):
            lo = mid
        else:
            high = mid
    return round(lo, -2)  # round to nearest $100 for presentation
