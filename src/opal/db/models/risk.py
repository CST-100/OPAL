"""Risk model."""

from enum import Enum

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class RiskStatus(str, Enum):
    """Risk status."""

    IDENTIFIED = "identified"
    ANALYZING = "analyzing"
    MITIGATING = "mitigating"
    MONITORING = "monitoring"
    CLOSED = "closed"


class Risk(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Risk ticket with probability x impact scoring."""

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[RiskStatus] = mapped_column(
        String(20), nullable=False, default=RiskStatus.IDENTIFIED
    )

    # Scoring: 1-5 each, score = probability x impact
    probability: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, comment="1-5 scale"
    )
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="1-5 scale")

    mitigation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional link to an issue for tracking
    linked_issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issue.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    linked_issue: Mapped["Issue | None"] = relationship("Issue", back_populates="risk")
    references: Mapped[list["RiskReference"]] = relationship(
        "RiskReference", back_populates="risk", cascade="all, delete-orphan"
    )

    @property
    def score(self) -> int:
        """Calculate risk score (probability x impact)."""
        return self.probability * self.impact

    @property
    def severity(self) -> str:
        """Get severity level based on score.

        1-5: low (green)
        6-12: medium (yellow)
        13-25: high (red)
        """
        score = self.score
        if score <= 5:
            return "low"
        elif score <= 12:
            return "medium"
        else:
            return "high"

    def __repr__(self) -> str:
        return f"<Risk(id={self.id}, title='{self.title}', score={self.score})>"
