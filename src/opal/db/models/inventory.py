"""Inventory model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class InventoryRecord(Base, IdMixin, TimestampMixin):
    """Inventory record tracking quantity at a location."""

    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, default=0
    )
    location: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Physical location identifier"
    )
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    last_counted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    part: Mapped["Part"] = relationship("Part", back_populates="inventory_records")

    def __repr__(self) -> str:
        return f"<InventoryRecord(id={self.id}, part_id={self.part_id}, qty={self.quantity}, loc='{self.location}')>"
