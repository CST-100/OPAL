"""Issue model."""

from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class IssueType(str, Enum):
    """Issue type classification."""

    NON_CONFORMANCE = "non_conformance"
    BUG = "bug"
    TASK = "task"
    IMPROVEMENT = "improvement"


class IssueStatus(str, Enum):
    """Issue status."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    DISPOSITION_PENDING = "disposition_pending"
    DISPOSITION_APPROVED = "disposition_approved"
    CLOSED = "closed"


class IssuePriority(str, Enum):
    """Issue priority level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DispositionType(str, Enum):
    """Disposition type for issue resolution."""

    USE_AS_IS = "use_as_is"
    REWORK = "rework"
    SCRAP = "scrap"
    RETURN_TO_VENDOR = "return_to_vendor"
    OTHER = "other"


class Issue(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Issue tracker entry.

    Issues can be auto-created from non-conformances during procedure execution,
    or created manually for bugs, tasks, and improvements.
    """

    issue_number: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True,
        comment="Human-readable issue ID (e.g., IT-001)"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_type: Mapped[IssueType] = mapped_column(
        String(20), nullable=False, default=IssueType.TASK
    )
    status: Mapped[IssueStatus] = mapped_column(
        String(30), nullable=False, default=IssueStatus.OPEN
    )
    priority: Mapped[IssuePriority] = mapped_column(
        String(20), nullable=False, default=IssuePriority.MEDIUM
    )

    # Type-specific fields
    should_be: Mapped[str | None] = mapped_column(Text, nullable=True, comment="NC: expected condition")
    is_condition: Mapped[str | None] = mapped_column(Text, nullable=True, comment="NC: actual condition")
    steps_to_reproduce: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Bug: repro steps")
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Bug: expected")
    actual_behavior: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Bug: actual")
    expected_benefit: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Improvement: benefit")

    # Disposition fields
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposition_type: Mapped[DispositionType | None] = mapped_column(String(30), nullable=True)
    disposition_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional links - an issue can link to any of these (or none)
    part_id: Mapped[int | None] = mapped_column(
        ForeignKey("part.id", ondelete="SET NULL"), nullable=True, index=True
    )
    procedure_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="SET NULL"), nullable=True, index=True
    )
    procedure_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("step_execution.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="For NC issues created during step execution",
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    disposition_approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    part: Mapped["Part | None"] = relationship("Part", back_populates="issues")
    procedure: Mapped["MasterProcedure | None"] = relationship(
        "MasterProcedure", back_populates="issues"
    )
    procedure_instance: Mapped["ProcedureInstance | None"] = relationship(
        "ProcedureInstance", back_populates="issues"
    )
    risk: Mapped["Risk | None"] = relationship("Risk", back_populates="linked_issue")
    references: Mapped[list["IssueReference"]] = relationship(
        "IssueReference", back_populates="issue", cascade="all, delete-orphan"
    )
    assigned_to: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assigned_to_id]
    )
    disposition_approved_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[disposition_approved_by_id]
    )
    comments: Mapped[list["IssueComment"]] = relationship(
        "IssueComment", back_populates="issue", cascade="all, delete-orphan",
        order_by="IssueComment.created_at"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="issue"
    )

    def __repr__(self) -> str:
        return f"<Issue(id={self.id}, type={self.issue_type}, title='{self.title}', status={self.status})>"
