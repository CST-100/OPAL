"""OPAL configuration via environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="sqlite:///./data/opal.db",
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

    # File uploads
    upload_dir: Path = Field(
        default=Path("./data/attachments"),
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
