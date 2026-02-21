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


# Lazy engine initialization - allows project config to be set before engine creation
_engine = None
_session_local = None


def _setup_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable SQLite foreign key support."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    """Get or create the database engine (lazy initialization)."""
    global _engine
    if _engine is None:
        from opal.config import get_active_settings
        settings = get_active_settings()
        _engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
            echo=settings.debug,
        )
        # Enable SQLite foreign key support
        if "sqlite" in settings.database_url:
            event.listen(_engine, "connect", _setup_sqlite_pragma)
    return _engine


def reinitialize_engine():
    """Reinitialize the engine (call after configure_for_project)."""
    global _engine, _session_local
    _engine = None
    _session_local = None


def SessionLocal():
    """Get a database session (lazy initialization)."""
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _session_local()


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database(engine=None) -> None:
    """Initialize or migrate the database.

    For new databases: creates all tables and stamps the current alembic revision.
    For existing databases: runs alembic upgrade to apply pending migrations.

    Args:
        engine: SQLAlchemy engine. If None, uses get_engine().
    """
    import logging

    from sqlalchemy import inspect

    logger = logging.getLogger("opal.db")

    if engine is None:
        engine = get_engine()

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    # Import all models to ensure metadata is populated
    import opal.db.models  # noqa: F401

    if not existing_tables:
        # New database: create all tables directly
        logger.info("Creating new database schema...")
        Base.metadata.create_all(engine)

        # Stamp alembic version so future migrations know the starting point
        _stamp_alembic_head(engine)
        logger.info("Database initialized at current schema version.")
    else:
        # Existing database: run migrations to apply any pending changes
        logger.info("Running database migrations...")
        _run_alembic_upgrade(engine)
        logger.info("Database migrations complete.")


def _get_alembic_config(engine=None):
    """Build an alembic Config object for programmatic use.

    Looks for migrations in the installed package or the project root.
    """
    from pathlib import Path

    from alembic.config import Config

    cfg = Config()

    # Find the migrations directory — try package resources first, then project root
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    migrations_dir = project_root / "migrations"

    if not migrations_dir.is_dir():
        # Bundled binary: migrations might be alongside the package
        import opal

        pkg_dir = Path(opal.__file__).resolve().parent
        for candidate in [
            pkg_dir.parent.parent / "migrations",
            pkg_dir.parent / "migrations",
            pkg_dir / "migrations",
        ]:
            if candidate.is_dir():
                migrations_dir = candidate
                break

    cfg.set_main_option("script_location", str(migrations_dir))

    if engine is not None:
        cfg.set_main_option("sqlalchemy.url", str(engine.url))

    return cfg


def _stamp_alembic_head(engine) -> None:
    """Stamp the alembic version table to the current head revision."""
    from alembic import command

    cfg = _get_alembic_config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.stamp(cfg, "head")


def _run_alembic_upgrade(engine) -> None:
    """Run alembic upgrade to head programmatically."""
    from alembic import command

    cfg = _get_alembic_config(engine)
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
