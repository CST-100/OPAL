"""FastAPI middleware configuration."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from opal.config import get_settings


class UserContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract user context from request headers."""

    async def dispatch(self, request: Request, call_next: any) -> Response:
        # Extract user ID from header if present
        user_id = request.headers.get("X-User-Id")
        if user_id:
            try:
                request.state.user_id = int(user_id)
            except ValueError:
                request.state.user_id = None
        else:
            request.state.user_id = None

        response = await call_next(request)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware (placeholder - disabled by default)."""

    def __init__(self, app: FastAPI, enabled: bool = False):
        super().__init__(app)
        self.enabled = enabled
        # TODO: Implement actual rate limiting when enabled

    async def dispatch(self, request: Request, call_next: any) -> Response:
        # Rate limiting logic would go here when enabled
        return await call_next(request)


class UserSelectionMiddleware(BaseHTTPMiddleware):
    """Redirect to /login if no opal_user_id cookie is set."""

    EXEMPT_PREFIXES = ("/login", "/logout", "/api/", "/static/", "/docs", "/favicon.ico")

    async def dispatch(self, request: Request, call_next: any) -> Response:
        path = request.url.path
        if any(path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)

        user_id = request.cookies.get("opal_user_id")
        if not user_id:
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the application."""
    settings = get_settings()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # User context middleware
    app.add_middleware(UserContextMiddleware)

    # User selection middleware (redirect to /login if no cookie)
    app.add_middleware(UserSelectionMiddleware)

    # Rate limiting middleware (disabled by default)
    app.add_middleware(RateLimitMiddleware, enabled=settings.rate_limit_enabled)
