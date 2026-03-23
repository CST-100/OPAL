"""Location model."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class Location(Base, IdMixin, TimestampMixin):
    """Physical location where inventory can be stored.

    Supports hierarchical structure (STORE > STORE-A1 > STORE-A1-BIN3).
    Each location gets a scannable OPALcode label.
    """

    code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True,
        comment="Scannable location code, e.g. STORE-A1, PAD-CART",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable name, e.g. Stockroom Shelf A1",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("location.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Parent location for hierarchy",
    )

    # Relationships
    parent: Mapped["Location | None"] = relationship(
        "Location", remote_side="Location.id", back_populates="children",
    )
    children: Mapped[list["Location"]] = relationship(
        "Location", back_populates="parent",
    )

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, code='{self.code}')>"
