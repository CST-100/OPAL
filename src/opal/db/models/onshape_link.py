"""Onshape integration models — linking Onshape parts to OPAL parts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class OnshapeLink(Base, IdMixin, TimestampMixin):
    """Maps an Onshape part to an OPAL Part (1:1).

    Stores Onshape identifiers needed to locate the part in the Onshape API,
    plus sync hashes for efficient change detection.
    """

    __tablename__ = "onshape_link"

    # FK to OPAL Part — unique so each Part has at most one Onshape link
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="OPAL Part this link references",
    )

    # Onshape identifiers
    document_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Onshape document ID",
    )
    element_id: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Onshape element (part studio / assembly) ID",
    )
    part_id_onshape: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Part ID within the Onshape element",
    )

    # Cached Onshape data for display without API calls
    onshape_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Part name as it appears in Onshape",
    )
    onshape_part_number: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Part number as set in Onshape",
    )

    # Sync tracking
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp of last successful sync",
    )
    pull_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of Onshape data at last pull (for change detection)",
    )
    push_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of OPAL ERP data at last push (for change detection)",
    )

    # Stale link tracking (Onshape part removed from BOM or deleted)
    stale: Mapped[bool] = mapped_column(
        default=False, nullable=False,
        comment="True if Onshape part was not found during last sync",
    )

    # Relationships
    part: Mapped["Part"] = relationship("Part", backref="onshape_link", uselist=False)  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<OnshapeLink(id={self.id}, part_id={self.part_id}, "
            f"doc={self.document_id}, onshape_name='{self.onshape_name}')>"
        )


class OnshapeSyncLog(Base, IdMixin):
    """Audit trail for Onshape sync operations."""

    __tablename__ = "onshape_sync_log"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When the sync operation started",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When the sync operation completed (null if still running or failed)",
    )
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="Sync direction: 'pull' or 'push'",
    )
    trigger: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="What triggered the sync: 'manual', 'poll', or 'webhook'",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running",
        comment="Sync status: 'running', 'success', 'partial', 'error'",
    )
    document_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Onshape document ID that was synced",
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True,
        comment="User who triggered the sync (null for automated syncs)",
    )

    # Counters
    parts_created: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    parts_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    bom_lines_created: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    bom_lines_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    bom_lines_removed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # Error details
    errors: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True,
        comment="Error details if sync failed or partially succeeded",
    )
    summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable sync summary",
    )

    def __repr__(self) -> str:
        return (
            f"<OnshapeSyncLog(id={self.id}, direction='{self.direction}', "
            f"status='{self.status}')>"
        )
