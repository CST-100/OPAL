"""Container (WIP/kit) models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class ContainerType(str, Enum):
    """Type of container."""

    KIT = "kit"  # Parts gathered for a procedure execution
    STAGING = "staging"  # Temporary staging area
    WIP = "wip"  # Work in progress assembly
    GENERAL = "general"  # General-purpose grouping


class ContainerStatus(str, Enum):
    """Container lifecycle status."""

    OPEN = "open"  # Accepting items
    SEALED = "sealed"  # Verified and ready for use
    CONSUMED = "consumed"  # All items consumed into a procedure
    ARCHIVED = "archived"  # No longer active


class Container(Base, IdMixin, TimestampMixin):
    """A physical or logical grouping of inventory items.

    Used for kitting (gathering parts for a procedure), staging,
    and WIP tracking. Each container gets a scannable OPALcode.
    """

    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True,
        comment="Unique container code, e.g. KIT-00001",
    )
    name: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Optional display name, e.g. Engine Build Kit",
    )
    container_type: Mapped[ContainerType] = mapped_column(
        String(20), nullable=False, default=ContainerType.GENERAL,
    )
    status: Mapped[ContainerStatus] = mapped_column(
        String(20), nullable=False, default=ContainerStatus.OPEN,
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Where this container physically is",
    )
    procedure_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Execution this container is kitted for",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    location: Mapped["Location | None"] = relationship("Location")
    procedure_instance: Mapped["ProcedureInstance | None"] = relationship("ProcedureInstance")
    items: Mapped[list["ContainerItem"]] = relationship(
        "ContainerItem", back_populates="container", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Container(id={self.id}, code='{self.code}', status={self.status})>"


class ContainerItem(Base, IdMixin, TimestampMixin):
    """An inventory item scanned into a container."""

    container_id: Mapped[int] = mapped_column(
        ForeignKey("container.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    inventory_record_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False,
    )
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    scanned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    container: Mapped["Container"] = relationship("Container", back_populates="items")
    inventory_record: Mapped["InventoryRecord"] = relationship("InventoryRecord")
    scanned_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ContainerItem(container_id={self.container_id}, inv={self.inventory_record_id}, qty={self.quantity})>"
