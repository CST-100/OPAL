"""Audit logging utilities."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect, MetaData
from sqlalchemy.orm import Session

from opal.db.models.audit import AuditAction, AuditLog


def get_model_dict(instance: Any) -> dict[str, Any]:
    """Convert SQLAlchemy model instance to dictionary.

    Excludes relationship attributes and includes only column values.
    Handles edge cases like column names conflicting with SQLAlchemy internals.
    Converts non-JSON-serializable types (Decimal, Enum, datetime) to serializable forms.
    """
    mapper = inspect(instance.__class__)
    result = {}

    for column in mapper.columns:
        # Use the column key (Python attribute name) to get the value
        attr_name = column.key
        value = getattr(instance, attr_name, None)

        # Skip SQLAlchemy internal objects that aren't actual data
        if isinstance(value, MetaData):
            continue

        # Convert datetime/date to ISO format for JSON serialization
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, date):
            value = value.isoformat()
        # Convert Decimal to float for JSON serialization
        elif isinstance(value, Decimal):
            value = float(value)
        # Convert Enum to its value for JSON serialization
        elif isinstance(value, Enum):
            value = value.value

        # Use column name (DB column) for consistency in audit logs
        result[column.name] = value

    return result


def get_changes(old_values: dict[str, Any], new_values: dict[str, Any]) -> dict[str, Any]:
    """Get only the changed values between old and new state."""
    changes = {}
    for key, new_value in new_values.items():
        old_value = old_values.get(key)
        if old_value != new_value:
            changes[key] = new_value
    return changes


def log_create(
    db: Session,
    instance: Any,
    user_id: int | None = None,
) -> AuditLog:
    """Log a create action."""
    new_values = get_model_dict(instance)

    audit_entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        table_name=instance.__tablename__,
        record_id=instance.id,
        action=AuditAction.CREATE,
        user_id=user_id,
        old_values=None,
        new_values=new_values,
    )
    db.add(audit_entry)
    return audit_entry


def log_update(
    db: Session,
    instance: Any,
    old_values: dict[str, Any],
    user_id: int | None = None,
) -> AuditLog | None:
    """Log an update action.

    Returns None if no changes were made.
    """
    new_values = get_model_dict(instance)
    changes = get_changes(old_values, new_values)

    if not changes:
        return None

    audit_entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        table_name=instance.__tablename__,
        record_id=instance.id,
        action=AuditAction.UPDATE,
        user_id=user_id,
        old_values=old_values,
        new_values=changes,
    )
    db.add(audit_entry)
    return audit_entry


def log_delete(
    db: Session,
    instance: Any,
    user_id: int | None = None,
) -> AuditLog:
    """Log a delete action."""
    old_values = get_model_dict(instance)

    audit_entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        table_name=instance.__tablename__,
        record_id=instance.id,
        action=AuditAction.DELETE,
        user_id=user_id,
        old_values=old_values,
        new_values=None,
    )
    db.add(audit_entry)
    return audit_entry


class AuditContext:
    """Context manager for tracking changes to a model instance.

    Usage:
        with AuditContext(db, instance, user_id) as ctx:
            instance.name = "new name"
            # Changes are automatically logged on exit
    """

    def __init__(
        self,
        db: Session,
        instance: Any,
        user_id: int | None = None,
    ):
        self.db = db
        self.instance = instance
        self.user_id = user_id
        self.old_values: dict[str, Any] = {}

    def __enter__(self) -> "AuditContext":
        self.old_values = get_model_dict(self.instance)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is None:
            log_update(self.db, self.instance, self.old_values, self.user_id)
