from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db.mongo import ensure_indexes
from . import activity_ws, auth_endpoints, chat, proposals, rest


def build_app() -> FastAPI:
    app = FastAPI(title="Reeve", version="0.1.0")

    # Vite dev server proxies /api/* through. CORS is permissive in dev — tighten
    # before any non-localhost deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        await ensure_indexes()

    app.include_router(auth_endpoints.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(proposals.router, prefix="/api")
    app.include_router(rest.router, prefix="/api")
    app.include_router(activity_ws.router, prefix="/api")

    return app
