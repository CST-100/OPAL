"""OPAL configuration via environment variables."""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from opal.project import ProjectConfig


def get_default_data_dir() -> Path:
    """Get the platform-appropriate default data directory.

    Resolution order:
    1. OPAL_DATA_DIR environment variable (if set)
    2. Platform-specific directory:
       - macOS:   ~/Library/Application Support/OPAL/
       - Linux:   $XDG_DATA_HOME/opal/ (default ~/.local/share/opal/)
       - Windows: %LOCALAPPDATA%\\OPAL\\

    Returns:
        Path to the data directory.
    """
    env_dir = os.environ.get("OPAL_DATA_DIR")
    if env_dir:
        return Path(env_dir)

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OPAL"
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "OPAL"
        return Path.home() / "AppData" / "Local" / "OPAL"
    else:
        # Linux / other Unix
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            return Path(xdg_data) / "opal"
        return Path.home() / ".local" / "share" / "opal"


def _default_database_url() -> str:
    data_dir = get_default_data_dir()
    return f"sqlite:///{data_dir / 'opal.db'}"


def _default_upload_dir() -> Path:
    return get_default_data_dir() / "attachments"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="OPAL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8080, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # Database
    database_url: str = Field(
        default_factory=_default_database_url,
        description="Database connection URL",
    )

    # Security
    allowed_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins",
    )
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")

    # Authentication
    auth_mode: str = Field(default="local", description="Auth mode: 'local' or 'exe'")

    # Onshape integration (off by default)
    onshape_access_key: str = Field(
        default="", description="Onshape API access key"
    )
    onshape_secret_key: str = Field(
        default="", description="Onshape API secret key"
    )
    onshape_base_url: str = Field(
        default="https://cad.onshape.com", description="Onshape API base URL"
    )
    onshape_poll_interval_minutes: int = Field(
        default=15, description="Minutes between automatic pull syncs (0 to disable)"
    )
    onshape_webhook_secret: str = Field(
        default="", description="Shared secret for Onshape webhook HMAC verification"
    )

    @property
    def onshape_enabled(self) -> bool:
        """True when Onshape API credentials are configured."""
        return bool(self.onshape_access_key and self.onshape_secret_key)

    # File uploads
    upload_dir: Path = Field(
        default_factory=_default_upload_dir,
        description="Directory for file uploads",
    )
    max_upload_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum upload file size in bytes",
    )
    allowed_mime_types: str = Field(
        default="image/jpeg,image/png,image/gif,application/pdf,text/plain,text/csv",
        description="Comma-separated list of allowed MIME types",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse allowed origins into a list."""
        if self.allowed_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def mime_types_list(self) -> list[str]:
        """Parse allowed MIME types into a list."""
        return [mime.strip() for mime in self.allowed_mime_types.split(",")]

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        # Ensure data directory exists for SQLite
        db_path = self.database_url.replace("sqlite:///", "")
        if db_path.startswith("./"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Runtime settings that can be modified by project config
_runtime_settings: Settings | None = None
_active_project: "ProjectConfig | None" = None


def configure_for_project(
    project: "ProjectConfig | None" = None,
    database_path: Path | str | None = None,
) -> Settings:
    """Configure settings for a specific project.

    Args:
        project: Project configuration to use.
        database_path: Explicit database path (overrides project).

    Returns:
        Configured Settings instance.
    """
    global _runtime_settings, _active_project

    base = get_settings()

    # Determine database URL
    if database_path:
        db_path = Path(database_path).resolve()
        database_url = f"sqlite:///{db_path}"
        upload_dir = db_path.parent / "attachments"
    elif project:
        database_url = project.database_url
        upload_dir = project.attachments_dir
    else:
        database_url = base.database_url
        upload_dir = base.upload_dir

    # Create new settings with overrides
    _runtime_settings = Settings(
        host=base.host,
        port=base.port,
        debug=base.debug,
        database_url=database_url,
        allowed_origins=base.allowed_origins,
        rate_limit_enabled=base.rate_limit_enabled,
        rate_limit_requests=base.rate_limit_requests,
        rate_limit_window=base.rate_limit_window,
        upload_dir=upload_dir,
        max_upload_size=base.max_upload_size,
        allowed_mime_types=base.allowed_mime_types,
        auth_mode=base.auth_mode,
        onshape_access_key=base.onshape_access_key,
        onshape_secret_key=base.onshape_secret_key,
        onshape_base_url=base.onshape_base_url,
        onshape_poll_interval_minutes=base.onshape_poll_interval_minutes,
        onshape_webhook_secret=base.onshape_webhook_secret,
    )
    _active_project = project

    return _runtime_settings


def get_active_settings() -> Settings:
    """Get the currently active settings (runtime or default)."""
    return _runtime_settings or get_settings()


def get_active_project() -> "ProjectConfig | None":
    """Get the currently active project configuration."""
    return _active_project
