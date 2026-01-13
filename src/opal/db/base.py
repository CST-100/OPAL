"""SQLAlchemy database setup."""

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, create_engine, event
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
)

from opal.config import get_settings


class Base(DeclarativeBase):
    """Base class for all database models."""

    type_annotation_map = {
        dict[str, Any]: JSON,
    }

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        # Convert CamelCase to snake_case
        name = cls.__name__
        result = [name[0].lower()]
        for char in name[1:]:
            if char.isupper():
                result.append("_")
                result.append(char.lower())
            else:
                result.append(char)
        return "".join(result)


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin for soft delete support."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        nullable=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if record is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark record as deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None


class IdMixin:
    """Mixin for auto-incrementing integer primary key."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


# Create engine from settings
settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=settings.debug,
)

# Enable SQLite foreign key support
if "sqlite" in settings.database_url:

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
