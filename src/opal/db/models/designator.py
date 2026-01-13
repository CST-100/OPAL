"""Designator sequence model for tracking sequential numbers."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from opal.db.base import Base, TimestampMixin


class DesignatorSequence(Base, TimestampMixin):
    """Tracks sequential counters for each designator type.

    Used to generate unique sequential identifiers like:
    - OPAL-00001 (physical items)
    - WO-00001 (work orders)
    - IT-00001 (issues)
    - RISK-00001 (risks)
    """

    __tablename__ = "designator_sequence"

    designator_type: Mapped[str] = mapped_column(
        String(10), primary_key=True, comment="OPAL, WO, IT, RISK"
    )
    last_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Last assigned sequence number"
    )

    def __repr__(self) -> str:
        return f"<DesignatorSequence(type={self.designator_type}, last={self.last_value})>"
