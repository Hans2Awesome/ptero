"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finance_core.db.connection import connect
from finance_core.db.migrations import run_migrations

from .config import Settings, get_settings
from .routes.auth import router as auth_router
from .routes.categories import router as categories_router
from .routes.debts import router as debts_router
from .routes.reports import router as reports_router
from .routes.transactions import router as transactions_router

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application, applying migrations on startup."""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        # Re-read settings at startup so tests and deployments can override the
        # database path without rebuilding the application object.
        connection = connect(get_settings().database_path)
        try:
            version = run_migrations(connection)
            logger.info("Database schema ready at version %s", version)
        finally:
            connection.close()
        yield

    application = FastAPI(
        title="Personal Finance API",
        description=(
            "Backend API for personal finance tracking with quick text input parsing."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=resolved_settings.allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(auth_router)
    application.include_router(transactions_router)
    application.include_router(categories_router)
    application.include_router(reports_router)
    application.include_router(debts_router)

    @application.get("/", tags=["Health"])
    def health_check() -> dict[str, str]:
        """Health check and API info."""

        return {
            "status": "online",
            "app": "Personal Finance API",
            "version": "1.0.0",
            "docs_url": "/docs",
        }

    return application


app = create_app()