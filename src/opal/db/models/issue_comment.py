"""Issue comment model."""

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class IssueComment(Base, IdMixin, TimestampMixin):
    """Comment / activity log entry on an issue."""

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issue.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")
    user: Mapped["User | None"] = relationship("User")
