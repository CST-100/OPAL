"""Attachment model."""

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class Attachment(Base, IdMixin, TimestampMixin):
    """File attachment stored in local filesystem."""

    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Original uploaded filename"
    )
    stored_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, comment="UUID-based filename on disk"
    )
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="'inline' = embedded in markdown content; 'reference' = downloadable doc; 'closeout' = end-item closeout photo surfaced in build reports; null = legacy/unscoped",
    )

    # Optional links - attachment can belong to instance, step, issue, procedure, or neither
    procedure_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="CASCADE"), nullable=True, index=True
    )
    step_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("step_execution.id", ondelete="CASCADE"), nullable=True, index=True
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issue.id", ondelete="CASCADE"), nullable=True, index=True
    )
    procedure_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Template-level scope: inline images in step instructions / procedure description",
    )

    # Relationships
    procedure_instance: Mapped["ProcedureInstance | None"] = relationship(
        "ProcedureInstance", back_populates="attachments"
    )
    step_execution: Mapped["StepExecution | None"] = relationship(
        "StepExecution", back_populates="attachments"
    )
    issue: Mapped["Issue | None"] = relationship("Issue", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id}, filename='{self.original_filename}', type='{self.mime_type}')>"
