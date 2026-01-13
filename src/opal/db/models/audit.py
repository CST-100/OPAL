"""Audit log model."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from opal.db.base import Base


class AuditAction(str, Enum):
    """Audit log action types."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AuditLog(Base):
    """Audit log entry for tracking all changes.

    Records every create/update/delete with old/new values as JSON.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # What changed
    table_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    action: Mapped[AuditAction] = mapped_column(String(20), nullable=False)

    # Who made the change
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Change details
    old_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Previous values (null for create)"
    )
    new_values: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="New values (null for delete)"
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, table={self.table_name}, record={self.record_id}, action={self.action})>"
