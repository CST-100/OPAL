"""FastAPI middleware configuration."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

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

    # Rate limiting middleware (disabled by default)
    app.add_middleware(RateLimitMiddleware, enabled=settings.rate_limit_enabled)
