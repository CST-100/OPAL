"""Purchase order models."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class PurchaseStatus(str, Enum):
    """Purchase order status."""

    DRAFT = "draft"
    ORDERED = "ordered"
    PARTIAL = "partial"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class Purchase(Base, IdMixin, TimestampMixin):
    """Purchase order."""

    # Reference number (e.g., PO-0001)
    reference: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True,
        comment="Unique PO reference like PO-0001"
    )

    # Supplier - keep legacy string field for backwards compatibility, add FK
    supplier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Link to Supplier entity (preferred)"
    )
    supplier_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Supplier's order reference code"
    )

    # Status and dates
    status: Mapped[PurchaseStatus] = mapped_column(
        String(20), nullable=False, default=PurchaseStatus.DRAFT
    )
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="Expected delivery date"
    )

    # Destination for received items
    destination: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Default location for received items"
    )

    # User tracking
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    received_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    lines: Mapped[list["PurchaseLine"]] = relationship(
        "PurchaseLine", back_populates="purchase", cascade="all, delete-orphan"
    )
    supplier_rel: Mapped["Supplier | None"] = relationship(
        "Supplier", back_populates="purchases"
    )
    created_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_id], back_populates="purchases_created"
    )
    received_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[received_by_id], back_populates="purchases_received"
    )

    @property
    def is_overdue(self) -> bool:
        """Check if PO is overdue (past target_date but not received)."""
        if not self.target_date:
            return False
        if self.status in (PurchaseStatus.RECEIVED, PurchaseStatus.CANCELLED):
            return False
        return date.today() > self.target_date

    def __repr__(self) -> str:
        return f"<Purchase(id={self.id}, ref='{self.reference}', status={self.status})>"


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
    destination: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Override location for this line"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

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
