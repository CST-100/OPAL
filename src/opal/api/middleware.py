"""FastAPI middleware configuration."""

import logging
from urllib.parse import quote

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from opal.config import get_active_settings, get_settings

logger = logging.getLogger(__name__)


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
    """Mode-aware auth middleware.

    local mode: redirect to /login if no opal_user_id cookie.
    exe mode: trust X-ExeDev-UserID / X-ExeDev-Email headers from proxy,
              auto-provision users, set cookies.
    """

    LOCAL_EXEMPT = ("/login", "/logout", "/api/", "/static/", "/docs", "/favicon.ico")
    EXE_EXEMPT = ("/api/", "/static/", "/docs", "/favicon.ico")

    async def dispatch(self, request: Request, call_next: any) -> Response:
        settings = get_active_settings()
        if settings.auth_mode == "exe":
            return await self._dispatch_exe(request, call_next)
        return await self._dispatch_local(request, call_next)

    async def _dispatch_local(self, request: Request, call_next: any) -> Response:
        """Local mode: check cookie, redirect to /login."""
        path = request.url.path
        if any(path.startswith(p) for p in self.LOCAL_EXEMPT):
            return await call_next(request)

        user_id = request.cookies.get("opal_user_id")
        if not user_id:
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)

    async def _dispatch_exe(self, request: Request, call_next: any) -> Response:
        """Exe mode: trust proxy headers, auto-provision users."""
        path = request.url.path
        if any(path.startswith(p) for p in self.EXE_EXEMPT):
            return await call_next(request)

        exe_user_id = request.headers.get("X-ExeDev-UserID")
        exe_email = request.headers.get("X-ExeDev-Email")

        if not exe_user_id or not exe_email:
            # No proxy headers — redirect to exe.dev login
            redirect_path = quote(str(request.url.path), safe="")
            return RedirectResponse(
                url=f"/__exe.dev/login?redirect={redirect_path}",
                status_code=302,
            )

        # Look up or create user
        user = await self._get_or_create_exe_user(exe_user_id, exe_email)
        if not user:
            return RedirectResponse(url="/__exe.dev/login", status_code=302)

        # Set cookies so the rest of the app works unchanged
        response = await call_next(request)

        max_age = 365 * 24 * 3600
        response.set_cookie("opal_user_id", str(user["id"]), max_age=max_age)
        response.set_cookie("opal_user_name", user["name"], max_age=max_age)
        response.set_cookie("opal_user_email", user["email"] or "", max_age=max_age)
        response.set_cookie("opal_user_is_admin", "1" if user["is_admin"] else "0", max_age=max_age)

        return response

    async def _get_or_create_exe_user(self, exe_user_id: str, exe_email: str) -> dict | None:
        """Look up user by exe_user_id, auto-create if not found."""
        from opal.db.models.user import User
        from opal.db.session import get_session

        with get_session() as db:
            user = db.query(User).filter(
                User.exe_user_id == exe_user_id,
                User.is_active == True,  # noqa: E712
            ).first()

            if user:
                # Update email if changed
                if user.email != exe_email:
                    user.email = exe_email
                    db.flush()
                return {"id": user.id, "name": user.name, "email": user.email, "is_admin": user.is_admin}

            # Auto-create: derive name from email local part
            local_part = exe_email.split("@")[0] if "@" in exe_email else exe_email
            name = local_part.replace(".", " ").replace("_", " ").replace("-", " ").title()

            # First user ever = admin
            is_first_user = db.query(User).count() == 0

            new_user = User(
                name=name,
                email=exe_email,
                exe_user_id=exe_user_id,
                is_active=True,
                is_admin=is_first_user,
            )
            db.add(new_user)
            db.flush()
            db.refresh(new_user)
            logger.info("Auto-provisioned exe user: %s (exe_user_id=%s)", name, exe_user_id)

            return {"id": new_user.id, "name": new_user.name, "email": new_user.email, "is_admin": new_user.is_admin}


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

    # User selection middleware (mode-aware: local or exe)
    app.add_middleware(UserSelectionMiddleware)

    # Rate limiting middleware (disabled by default)
    app.add_middleware(RateLimitMiddleware, enabled=settings.rate_limit_enabled)
