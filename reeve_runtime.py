"""Reeve runtime entrypoint.

The original scaffold (in-memory stores, sync LLM loop) has been fleshed
out into the `reeve` package. This file stays as the FastAPI app object
that `uvicorn reeve_runtime:app` boots."""
from reeve.api import build_app

app = build_app()
