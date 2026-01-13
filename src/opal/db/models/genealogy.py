"""Assembly genealogy model for tracking component relationships."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class AssemblyComponent(Base, IdMixin, TimestampMixin):
    """Links produced assemblies to their consumed components.

    When a BUILD procedure produces an assembly, this table records
    which component OPAL numbers went into making that assembly.

    This enables full genealogy tracking:
    - Forward: "What components made up this assembly?"
    - Reverse: "Which assemblies contain this component?"
    """

    __tablename__ = "assembly_component"

    # The production record that created the assembly
    production_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_production.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The production record (assembly being built)"
    )

    # The consumption record for the component used
    consumption_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_consumption.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The consumption record (component used)"
    )

    # Denormalized OPAL number for efficient queries
    component_opal_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="OPAL number of the consumed component (denormalized)"
    )

    # Quantity of this component used in the assembly
    quantity_used: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4),
        nullable=False,
        comment="Quantity of this component used"
    )

    # Relationships
    production: Mapped["InventoryProduction"] = relationship(
        "InventoryProduction",
        back_populates="assembly_components"
    )
    consumption: Mapped["InventoryConsumption"] = relationship(
        "InventoryConsumption",
        back_populates="assembly_usage"
    )

    def __repr__(self) -> str:
        return f"<AssemblyComponent(production_id={self.production_id}, component={self.component_opal_number}, qty={self.quantity_used})>"
