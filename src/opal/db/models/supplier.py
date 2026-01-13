"""Supplier model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Supplier(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """External supplier/vendor company."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, unique=True, comment="Short code like SUP001"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    purchases: Mapped[list["Purchase"]] = relationship("Purchase", back_populates="supplier_rel")

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}')>"
