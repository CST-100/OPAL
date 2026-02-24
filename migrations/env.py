"""Alembic migration environment."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from opal.config import get_settings
from opal.db.base import Base

# Import all models to ensure they're registered with Base.metadata
from opal.db.models import (  # noqa: F401
    AuditLog,
    Attachment,
    DataPoint,
    Dataset,
    InventoryRecord,
    Issue,
    Kit,
    MasterProcedure,
    OnshapeLink,
    OnshapeSyncLog,
    Part,
    ProcedureInstance,
    ProcedureStep,
    ProcedureVersion,
    Purchase,
    PurchaseLine,
    Risk,
    StepExecution,
    User,
)

# Alembic Config object
config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata

# Get database URL from settings
settings = get_settings()


def get_url() -> str:
    """Get database URL from settings."""
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    Supports receiving a connection via config.attributes for programmatic use.
    """
    # If a connection was passed programmatically (e.g. from init_database),
    # use it directly instead of creating a new engine.
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        configuration = config.get_section(config.config_ini_section) or {}
        configuration["sqlalchemy.url"] = get_url()

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,  # Required for SQLite ALTER TABLE
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
