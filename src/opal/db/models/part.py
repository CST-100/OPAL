"""Part model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from opal.db.models.user import User


class TrackingType(str, Enum):
    """How inventory for this part is tracked."""

    BULK = "bulk"  # One OPAL number for a batch/box (e.g., fasteners)
    SERIALIZED = "serialized"  # Each unit gets its own OPAL number


class Part(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Part in the inventory system.

    IDs are system-unique, auto-incrementing, and never reused.
    """

    internal_pn: Mapped[str | None] = mapped_column(
        String(50), nullable=True, unique=True, index=True,
        comment="Internal part number from project config (e.g., PO/1-001)"
    )
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
    tracking_type: Mapped[TrackingType] = mapped_column(
        String(20), nullable=False, default=TrackingType.SERIALIZED,
        comment="bulk = one OPAL per batch, serialized = one OPAL per unit (default)"
    )

    # Tiered inventory classification (1=Flight, 2=Ground, 3=Loose by default)
    tier: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, index=True,
        comment="Inventory tier level (1=Flight, 2=Ground, 3=Loose)"
    )

    # Assembly hierarchy - parts can contain other parts
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("part.id"), nullable=True, index=True,
        comment="Parent assembly this part belongs to"
    )

    # Relationships
    inventory_records: Mapped[list["InventoryRecord"]] = relationship(
        "InventoryRecord", back_populates="part", cascade="all, delete-orphan"
    )
    purchase_lines: Mapped[list["PurchaseLine"]] = relationship(
        "PurchaseLine", back_populates="part"
    )
    kits: Mapped[list["Kit"]] = relationship("Kit", back_populates="part")
    step_kits: Mapped[list["StepKit"]] = relationship("StepKit", back_populates="part")
    procedure_outputs: Mapped[list["ProcedureOutput"]] = relationship(
        "ProcedureOutput", back_populates="part"
    )
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="part")
    test_templates: Mapped[list["TestTemplate"]] = relationship(
        "TestTemplate", back_populates="part", cascade="all, delete-orphan"
    )

    # Self-referential relationships for assembly hierarchy
    parent: Mapped["Part | None"] = relationship(
        "Part", remote_side="Part.id", back_populates="children",
        foreign_keys=[parent_id]
    )
    children: Mapped[list["Part"]] = relationship(
        "Part", back_populates="parent", foreign_keys=[parent_id]
    )

    # Requirements assigned to this part
    requirements: Mapped[list["PartRequirement"]] = relationship(
        "PartRequirement", back_populates="part", cascade="all, delete-orphan"
    )

    # BOM: components contained in this assembly
    bom_lines: Mapped[list["BOMLine"]] = relationship(
        "BOMLine", back_populates="assembly",
        foreign_keys="BOMLine.assembly_id",
        cascade="all, delete-orphan"
    )

    # BOM: assemblies this part is used in
    used_in: Mapped[list["BOMLine"]] = relationship(
        "BOMLine", back_populates="component",
        foreign_keys="BOMLine.component_id"
    )

    def __repr__(self) -> str:
        return f"<Part(id={self.id}, name='{self.name}', tier={self.tier})>"


class PartRequirement(Base, IdMixin, TimestampMixin):
    """Links a part to a project requirement.

    Requirements are defined in the project config (opal.project.yaml).
    This tracks which requirements apply to which parts and their status.
    """

    __tablename__ = "part_requirements"

    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Requirement ID from project config (e.g., REQ-001)"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open",
        comment="open, verified, waived, not_applicable"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )

    # Relationships
    part: Mapped["Part"] = relationship("Part", back_populates="requirements")
    verified_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<PartRequirement(part_id={self.part_id}, requirement_id='{self.requirement_id}', status='{self.status}')>"


class BOMLine(Base, IdMixin, TimestampMixin):
    """Bill of Materials line item - quantity of a component in an assembly.

    This defines the design-level BOM structure (what parts go into an assembly).
    Different from genealogy.AssemblyComponent which tracks actual instance usage.
    """

    __tablename__ = "bom_lines"

    assembly_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True,
        comment="The assembly (parent part)"
    )
    component_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True,
        comment="The component (child part)"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="Number of this component in the assembly"
    )
    reference_designator: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Reference designator (e.g., R1, C3, U2)"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    assembly: Mapped["Part"] = relationship(
        "Part", back_populates="bom_lines", foreign_keys=[assembly_id]
    )
    component: Mapped["Part"] = relationship(
        "Part", back_populates="used_in", foreign_keys=[component_id]
    )

    def __repr__(self) -> str:
        return f"<BOMLine(assembly_id={self.assembly_id}, component_id={self.component_id}, qty={self.quantity})>"
