"""Importing this package registers every tool via decorator side effects."""
from . import (  # noqa: F401
    analysis,
    buy_box,
    comps,
    dispatch,
    gated,
    pipeline,
    submit,
)
