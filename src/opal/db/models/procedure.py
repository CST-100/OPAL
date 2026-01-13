"""Procedure models."""

from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class ProcedureStatus(str, Enum):
    """Master procedure status."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class MasterProcedure(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Master procedure template."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProcedureStatus] = mapped_column(
        String(20), nullable=False, default=ProcedureStatus.DRAFT
    )
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_version.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        comment="Points to latest published version",
    )

    # Relationships
    steps: Mapped[list["ProcedureStep"]] = relationship(
        "ProcedureStep",
        back_populates="procedure",
        cascade="all, delete-orphan",
        order_by="ProcedureStep.order",
    )
    versions: Mapped[list["ProcedureVersion"]] = relationship(
        "ProcedureVersion",
        back_populates="procedure",
        foreign_keys="ProcedureVersion.procedure_id",
        cascade="all, delete-orphan",
    )
    current_version: Mapped["ProcedureVersion | None"] = relationship(
        "ProcedureVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    kits: Mapped[list["Kit"]] = relationship(
        "Kit", back_populates="procedure", cascade="all, delete-orphan"
    )
    instances: Mapped[list["ProcedureInstance"]] = relationship(
        "ProcedureInstance", back_populates="procedure"
    )
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="procedure")

    def __repr__(self) -> str:
        return f"<MasterProcedure(id={self.id}, name='{self.name}', status={self.status})>"


class ProcedureStep(Base, IdMixin, TimestampMixin):
    """Step within a master procedure."""

    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, comment="Position in sequence")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Markdown")
    required_data_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Defines what data to capture"
    )
    is_contingency: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="Only shown if NC logged"
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship(
        "MasterProcedure", back_populates="steps"
    )

    def __repr__(self) -> str:
        return f"<ProcedureStep(id={self.id}, order={self.order}, title='{self.title}')>"


class ProcedureVersion(Base, IdMixin, TimestampMixin):
    """Immutable snapshot of a procedure at publish time."""

    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="1, 2, 3... per procedure"
    )
    content: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Full snapshot of steps at publish time"
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship(
        "MasterProcedure",
        back_populates="versions",
        foreign_keys=[procedure_id],
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="procedure_versions"
    )
    instances: Mapped[list["ProcedureInstance"]] = relationship(
        "ProcedureInstance", back_populates="version"
    )

    def __repr__(self) -> str:
        return f"<ProcedureVersion(id={self.id}, procedure_id={self.procedure_id}, v{self.version_number})>"


class Kit(Base, IdMixin, TimestampMixin):
    """Bill of materials for a procedure."""

    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_required: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False
    )

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship("MasterProcedure", back_populates="kits")
    part: Mapped["Part"] = relationship("Part", back_populates="kits")

    def __repr__(self) -> str:
        return f"<Kit(procedure_id={self.procedure_id}, part_id={self.part_id}, qty={self.quantity_required})>"
