"""Purchase order models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class PurchaseStatus(str, Enum):
    """Purchase order status."""

    DRAFT = "draft"
    ORDERED = "ordered"
    PARTIAL = "partial"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Purchase(Base, IdMixin, TimestampMixin):
    """Purchase order."""

    supplier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[PurchaseStatus] = mapped_column(
        String(20), nullable=False, default=PurchaseStatus.DRAFT
    )
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    lines: Mapped[list["PurchaseLine"]] = relationship(
        "PurchaseLine", back_populates="purchase", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Purchase(id={self.id}, supplier='{self.supplier}', status={self.status})>"


class PurchaseLine(Base, IdMixin, TimestampMixin):
    """Line item on a purchase order."""

    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchase.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty_ordered: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False
    )
    qty_received: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, default=0
    )
    unit_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=4), nullable=True
    )

    # Relationships
    purchase: Mapped["Purchase"] = relationship("Purchase", back_populates="lines")
    part: Mapped["Part"] = relationship("Part", back_populates="purchase_lines")

    @property
    def qty_outstanding(self) -> Decimal:
        """Quantity still to be received."""
        return self.qty_ordered - self.qty_received

    @property
    def is_complete(self) -> bool:
        """Check if line is fully received."""
        return self.qty_received >= self.qty_ordered

    def __repr__(self) -> str:
        return f"<PurchaseLine(id={self.id}, part_id={self.part_id}, ordered={self.qty_ordered}, received={self.qty_received})>"
