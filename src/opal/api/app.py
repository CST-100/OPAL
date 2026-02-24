"""FastAPI application factory."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from opal.api.middleware import setup_middleware
from opal.api.routes import router as api_router
from opal.config import get_settings
from opal.web.routes import router as web_router

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "web" / "templates"
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"

# Jinja2 templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    settings = get_settings()
    settings.ensure_directories()

    # Start Onshape polling if enabled
    polling_task: asyncio.Task | None = None
    if settings.onshape_enabled and settings.onshape_poll_interval_minutes > 0:
        try:
            from opal.integrations.onshape.polling import onshape_polling_loop

            polling_task = asyncio.create_task(
                onshape_polling_loop(settings.onshape_poll_interval_minutes)
            )
            logging.getLogger(__name__).info(
                "Onshape polling enabled (every %d min)",
                settings.onshape_poll_interval_minutes,
            )
        except Exception:
            logging.getLogger(__name__).warning("Failed to start Onshape polling", exc_info=True)

    yield

    # Cancel polling on shutdown
    if polling_task and not polling_task.done():
        polling_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await polling_task


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    import logging

    settings = get_settings()
    logging.getLogger(__name__).info("OPAL auth_mode=%s", settings.auth_mode)

    app = FastAPI(
        title="OPAL",
        description="Operations, Procedures, Assets, Logistics - ERP for small teams",
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    # Setup middleware
    setup_middleware(app)

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include API routes
    app.include_router(api_router, prefix="/api")

    # Include web routes
    app.include_router(web_router)

    return app


# Create application instance
app = create_app()
