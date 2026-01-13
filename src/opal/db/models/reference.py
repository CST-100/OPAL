"""Cross-reference models for linking Issues and Risks to OPAL/WO numbers."""

from enum import Enum

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class ReferenceType(str, Enum):
    """Type of reference being linked."""

    OPAL = "opal"  # Reference to an OPAL number (physical item)
    WORK_ORDER = "work_order"  # Reference to a WO number (procedure instance)


class IssueReference(Base, IdMixin, TimestampMixin):
    """Links an issue to OPAL numbers or work orders.

    Enables questions like:
    - "What issues affect OPAL-00042?"
    - "What issues are linked to WO-00015?"
    """

    __tablename__ = "issue_reference"
    __table_args__ = (
        UniqueConstraint('issue_id', 'reference_type', 'reference_value',
                         name='uq_issue_reference_unique'),
    )

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issue.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    reference_type: Mapped[ReferenceType] = mapped_column(
        String(20), nullable=False, comment="opal or work_order"
    )
    reference_value: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="The OPAL-XXXXX or WO-XXXXX value"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="references")

    def __repr__(self) -> str:
        return f"<IssueReference(issue_id={self.issue_id}, {self.reference_type}={self.reference_value})>"


class RiskReference(Base, IdMixin, TimestampMixin):
    """Links a risk to OPAL numbers or work orders.

    Enables questions like:
    - "What risks affect OPAL-00042?"
    - "What risks are linked to WO-00015?"
    """

    __tablename__ = "risk_reference"
    __table_args__ = (
        UniqueConstraint('risk_id', 'reference_type', 'reference_value',
                         name='uq_risk_reference_unique'),
    )

    risk_id: Mapped[int] = mapped_column(
        ForeignKey("risk.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    reference_type: Mapped[ReferenceType] = mapped_column(
        String(20), nullable=False, comment="opal or work_order"
    )
    reference_value: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="The OPAL-XXXXX or WO-XXXXX value"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    risk: Mapped["Risk"] = relationship("Risk", back_populates="references")

    def __repr__(self) -> str:
        return f"<RiskReference(risk_id={self.risk_id}, {self.reference_type}={self.reference_value})>"
