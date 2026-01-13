"""FastAPI application factory."""

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
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

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
