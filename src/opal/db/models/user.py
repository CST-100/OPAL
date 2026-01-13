"""User model."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin):
    """User model for tracking who performs actions.

    Note: Authentication not implemented yet - users selected via UI dropdown.
    """

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships (back-references)
    procedure_versions: Mapped[list["ProcedureVersion"]] = relationship(
        "ProcedureVersion", back_populates="created_by_user"
    )
    procedure_instances: Mapped[list["ProcedureInstance"]] = relationship(
        "ProcedureInstance", back_populates="started_by_user"
    )
    step_executions: Mapped[list["StepExecution"]] = relationship(
        "StepExecution", back_populates="completed_by_user"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name='{self.name}')>"
