"""Procedure execution models."""

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class InstanceStatus(str, Enum):
    """Procedure instance status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    """Step execution status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class ProcedureInstance(Base, IdMixin, TimestampMixin):
    """Execution of a specific procedure version."""

    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version_id: Mapped[int] = mapped_column(
        ForeignKey("procedure_version.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Locked at start",
    )
    work_order_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True, comment="For grouping related instances"
    )
    status: Mapped[InstanceStatus] = mapped_column(
        String(20), nullable=False, default=InstanceStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship(
        "MasterProcedure", back_populates="instances"
    )
    version: Mapped["ProcedureVersion"] = relationship(
        "ProcedureVersion", back_populates="instances"
    )
    started_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="procedure_instances"
    )
    step_executions: Mapped[list["StepExecution"]] = relationship(
        "StepExecution",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="StepExecution.step_number",
    )
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="procedure_instance")
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="procedure_instance"
    )

    @property
    def duration_seconds(self) -> int | None:
        """Calculate duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None

    def __repr__(self) -> str:
        return f"<ProcedureInstance(id={self.id}, procedure_id={self.procedure_id}, status={self.status})>"


class StepExecution(Base, IdMixin, TimestampMixin):
    """Execution of a single step within a procedure instance."""

    instance_id: Mapped[int] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="References step order from version snapshot"
    )
    status: Mapped[StepStatus] = mapped_column(
        String(20), nullable=False, default=StepStatus.PENDING
    )
    data_captured: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Values matching step's required_data_schema"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    instance: Mapped["ProcedureInstance"] = relationship(
        "ProcedureInstance", back_populates="step_executions"
    )
    completed_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="step_executions"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="step_execution"
    )

    @property
    def duration_seconds(self) -> int | None:
        """Calculate duration in seconds if completed."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return None

    def __repr__(self) -> str:
        return f"<StepExecution(id={self.id}, instance_id={self.instance_id}, step={self.step_number}, status={self.status})>"
