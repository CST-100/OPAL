"""Part model."""

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Part(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Part in the inventory system.

    IDs are system-unique, auto-incrementing, and never reused.
    """

    external_pn: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="Manufacturer/supplier part number"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    unit_of_measure: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ea", comment="ea, kg, m, etc."
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON, nullable=True, comment="Flexible additional fields"
    )

    # Relationships
    inventory_records: Mapped[list["InventoryRecord"]] = relationship(
        "InventoryRecord", back_populates="part", cascade="all, delete-orphan"
    )
    purchase_lines: Mapped[list["PurchaseLine"]] = relationship(
        "PurchaseLine", back_populates="part"
    )
    kits: Mapped[list["Kit"]] = relationship("Kit", back_populates="part")
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="part")

    def __repr__(self) -> str:
        return f"<Part(id={self.id}, name='{self.name}', external_pn='{self.external_pn}')>"
