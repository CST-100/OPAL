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


class ProcedureType(str, Enum):
    """Type of procedure."""

    OP = "op"  # Work order, no output
    BUILD = "build"  # Produces assembly output


class MasterProcedure(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Master procedure template."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedure_type: Mapped[ProcedureType] = mapped_column(
        String(20), nullable=False, default=ProcedureType.OP,
        comment="op = work order, build = produces assembly"
    )
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
    outputs: Mapped[list["ProcedureOutput"]] = relationship(
        "ProcedureOutput", back_populates="procedure", cascade="all, delete-orphan"
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
    parent_step_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_step.id", ondelete="CASCADE"), nullable=True, index=True,
        comment="NULL = top-level OP, set = sub-step"
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, comment="Position in sequence")
    step_number: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1", comment="Display number: 1, 1.1, 1.2, 2"
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="0 = major OP, 1 = sub-step"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Markdown")
    required_data_schema: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Defines what data to capture"
    )
    is_contingency: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="Only shown if NC logged"
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workcenter_id: Mapped[int | None] = mapped_column(
        ForeignKey("workcenter.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Default workcenter for this step"
    )

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship(
        "MasterProcedure", back_populates="steps"
    )
    parent_step: Mapped["ProcedureStep | None"] = relationship(
        "ProcedureStep", remote_side="ProcedureStep.id", back_populates="sub_steps"
    )
    sub_steps: Mapped[list["ProcedureStep"]] = relationship(
        "ProcedureStep", back_populates="parent_step", cascade="all, delete-orphan"
    )
    workcenter: Mapped["Workcenter | None"] = relationship(
        "Workcenter", back_populates="procedure_steps"
    )
    step_kits: Mapped[list["StepKit"]] = relationship(
        "StepKit", back_populates="step", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ProcedureStep(id={self.id}, step={self.step_number}, title='{self.title}')>"


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
    """Bill of materials for a procedure (parts consumed)."""

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


class ProcedureOutput(Base, IdMixin, TimestampMixin):
    """Output parts produced by a procedure (assemblies)."""

    procedure_id: Mapped[int] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="RESTRICT"), nullable=False, index=True,
        comment="The part/assembly that this procedure produces"
    )
    quantity_produced: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, default=1
    )

    # Relationships
    procedure: Mapped["MasterProcedure"] = relationship("MasterProcedure", back_populates="outputs")
    part: Mapped["Part"] = relationship("Part", back_populates="procedure_outputs")

    def __repr__(self) -> str:
        return f"<ProcedureOutput(procedure_id={self.procedure_id}, part_id={self.part_id}, qty={self.quantity_produced})>"


class UsageType(str, Enum):
    """How a part is used in a step."""

    CONSUME = "consume"  # Part is consumed/installed (inventory decremented)
    TOOLING = "tooling"  # Part is used but returned (GSE, fixtures)


class StepKit(Base, IdMixin, TimestampMixin):
    """Parts required at a specific step."""

    step_id: Mapped[int] = mapped_column(
        ForeignKey("procedure_step.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity_required: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False
    )
    usage_type: Mapped[UsageType] = mapped_column(
        String(20), nullable=False, default=UsageType.CONSUME,
        comment="consume = inventory decremented, tooling = reused"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    step: Mapped["ProcedureStep"] = relationship("ProcedureStep", back_populates="step_kits")
    part: Mapped["Part"] = relationship("Part", back_populates="step_kits")

    def __repr__(self) -> str:
        return f"<StepKit(step_id={self.step_id}, part_id={self.part_id}, usage={self.usage_type})>"
