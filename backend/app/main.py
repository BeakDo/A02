from __future__ import annotations

from .compat import ensure_runtime_compatibility

ensure_runtime_compatibility()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.routes import router
from .core.config import settings


def create_application() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.include_router(router, prefix=settings.api_v1_prefix)

    if settings.backend_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.backend_cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    return app


app = create_application()
