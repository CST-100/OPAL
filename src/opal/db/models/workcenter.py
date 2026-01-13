"""Workcenter model."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class Workcenter(Base, IdMixin, TimestampMixin):
    """Work location where steps are performed."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, comment="Short code like AB1, CR"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Physical location"
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    procedure_steps: Mapped[list["ProcedureStep"]] = relationship(
        "ProcedureStep", back_populates="workcenter"
    )
    step_executions: Mapped[list["StepExecution"]] = relationship(
        "StepExecution", back_populates="workcenter"
    )

    def __repr__(self) -> str:
        return f"<Workcenter(id={self.id}, code='{self.code}', name='{self.name}')>"
