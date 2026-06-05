"""Period helpers — date range tuples that the tools accept and return."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def iso_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def last_n_days(n: int, *, end: date | None = None) -> tuple[str, str]:
    e = end or datetime.now(timezone.utc).date()
    s = e - timedelta(days=n)
    return s.isoformat(), e.isoformat()


def month_to_date(*, today: date | None = None) -> tuple[str, str]:
    t = today or datetime.now(timezone.utc).date()
    return t.replace(day=1).isoformat(), t.isoformat()
