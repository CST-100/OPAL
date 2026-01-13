"""Dataset models."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Dataset(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Dataset for collecting and graphing data points."""

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Defines field names, types, and constraints"
    )

    # Optional link to a procedure
    procedure_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_procedure.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="e.g., QC measurements for procedure X",
    )

    # Relationships
    data_points: Mapped[list["DataPoint"]] = relationship(
        "DataPoint", back_populates="dataset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, name='{self.name}')>"


class DataPoint(Base, IdMixin, TimestampMixin):
    """Single data point in a dataset."""

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    values: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="Data matching dataset schema"
    )

    # Optional source tracking
    step_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("step_execution.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="If captured during step execution",
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="data_points")

    def __repr__(self) -> str:
        return f"<DataPoint(id={self.id}, dataset_id={self.dataset_id}, recorded_at={self.recorded_at})>"
