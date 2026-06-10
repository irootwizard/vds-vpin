from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vpin_backend.api.routes import crypto, health, models, session
from vpin_backend.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="vPIN Backend",
        version="0.1.0",
        description="MVP API for vPIN homomorphic inference and CP-SNARK bridge",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(crypto.router, prefix="/api/v1/crypto")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(session.router, prefix="/api/v1")

    @app.on_event("startup")
    async def _startup() -> None:
        settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
        (settings.resolved_data_dir / "models").mkdir(exist_ok=True)

    return app
