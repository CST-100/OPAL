"""Inventory model."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opal.db.base import Base, IdMixin, TimestampMixin


class SourceType(str, Enum):
    """Source of an inventory record."""

    PURCHASE = "purchase"  # Received from a purchase order
    PRODUCTION = "production"  # Produced by a procedure
    MANUAL = "manual"  # Manual entry/adjustment
    TRANSFER = "transfer"  # Transferred from another location


class InventoryRecord(Base, IdMixin, TimestampMixin):
    """Inventory record tracking quantity at a location.

    Each record has a unique OPAL number for traceability.
    """

    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, default=0
    )
    location: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Physical location identifier"
    )
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    last_counted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # OPAL number for traceability (unique identifier for physical item/batch)
    opal_number: Mapped[str | None] = mapped_column(
        String(20), nullable=True, unique=True, index=True,
        comment="Unique identifier like OPAL-00001"
    )

    # Source tracking - where did this inventory come from?
    source_type: Mapped[SourceType | None] = mapped_column(
        String(20), nullable=True, comment="purchase, production, manual, transfer"
    )
    source_purchase_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_line.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Link to PO line if from purchase"
    )
    source_production_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_production.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Link to production record if produced"
    )

    # Relationships
    part: Mapped["Part"] = relationship("Part", back_populates="inventory_records")
    consumptions: Mapped[list["InventoryConsumption"]] = relationship(
        "InventoryConsumption", back_populates="inventory_record"
    )
    productions: Mapped[list["InventoryProduction"]] = relationship(
        "InventoryProduction", foreign_keys="InventoryProduction.inventory_record_id",
        back_populates="inventory_record"
    )
    test_results: Mapped[list["StockTestResult"]] = relationship(
        "StockTestResult", back_populates="inventory_record", cascade="all, delete-orphan"
    )
    source_purchase_line: Mapped["PurchaseLine | None"] = relationship(
        "PurchaseLine", foreign_keys=[source_purchase_line_id], backref="inventory_records"
    )
    source_production: Mapped["InventoryProduction | None"] = relationship(
        "InventoryProduction", foreign_keys=[source_production_id],
        overlaps="productions,inventory_record"
    )

    def __repr__(self) -> str:
        return f"<InventoryRecord(id={self.id}, part_id={self.part_id}, qty={self.quantity}, loc='{self.location}')>"


class ConsumptionType(str, Enum):
    """Type of inventory consumption."""

    PROCEDURE = "procedure"  # Consumed during procedure execution
    ADJUSTMENT = "adjustment"  # Manual adjustment
    SCRAP = "scrap"  # Scrapped/damaged


class UsageType(str, Enum):
    """How a part was used during execution."""

    CONSUME = "consume"  # Part was consumed/installed
    TOOLING = "tooling"  # Part was used but returned (GSE)


class InventoryConsumption(Base, IdMixin, TimestampMixin):
    """Record of inventory being consumed (deducted)."""

    inventory_record_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, comment="Positive value = consumed"
    )
    consumption_type: Mapped[ConsumptionType] = mapped_column(
        String(20), nullable=False, default=ConsumptionType.PROCEDURE
    )
    usage_type: Mapped[UsageType] = mapped_column(
        String(20), nullable=False, default=UsageType.CONSUME,
        comment="consume = permanent, tooling = returned"
    )
    procedure_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("step_execution.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Which step consumed this part"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    consumed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    inventory_record: Mapped["InventoryRecord"] = relationship(
        "InventoryRecord", back_populates="consumptions"
    )
    procedure_instance: Mapped["ProcedureInstance | None"] = relationship(
        "ProcedureInstance", back_populates="consumptions"
    )
    step_execution: Mapped["StepExecution | None"] = relationship(
        "StepExecution", back_populates="consumptions"
    )
    consumed_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="consumptions"
    )
    assembly_usage: Mapped[list["AssemblyComponent"]] = relationship(
        "AssemblyComponent", back_populates="consumption"
    )

    def __repr__(self) -> str:
        return f"<InventoryConsumption(id={self.id}, inv_id={self.inventory_record_id}, qty={self.quantity})>"


class InventoryProduction(Base, IdMixin, TimestampMixin):
    """Record of inventory being produced (created by a procedure)."""

    inventory_record_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, comment="Positive value = produced"
    )
    procedure_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("procedure_instance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    serial_number: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True, comment="Serial for trackable assemblies"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    produced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    inventory_record: Mapped["InventoryRecord"] = relationship(
        "InventoryRecord", foreign_keys=[inventory_record_id], back_populates="productions"
    )
    procedure_instance: Mapped["ProcedureInstance | None"] = relationship(
        "ProcedureInstance", back_populates="productions"
    )
    produced_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="productions"
    )
    assembly_components: Mapped[list["AssemblyComponent"]] = relationship(
        "AssemblyComponent", back_populates="production"
    )

    def __repr__(self) -> str:
        return f"<InventoryProduction(id={self.id}, inv_id={self.inventory_record_id}, qty={self.quantity})>"


class TestResult(str, Enum):
    """Result of a stock test."""

    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


class TestTemplate(Base, IdMixin, TimestampMixin):
    """Predefined test template for a part.

    Defines tests that should be performed on stock items of a particular part.
    """

    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Test name")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="Whether this test is mandatory"
    )
    test_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="boolean",
        comment="boolean, numeric, text"
    )
    min_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=4), nullable=True, comment="For numeric tests"
    )
    max_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=15, scale=4), nullable=True, comment="For numeric tests"
    )
    unit: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Unit for numeric tests"
    )
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    # Relationships
    part: Mapped["Part"] = relationship("Part", back_populates="test_templates")
    test_results: Mapped[list["StockTestResult"]] = relationship(
        "StockTestResult", back_populates="template"
    )

    def __repr__(self) -> str:
        return f"<TestTemplate(id={self.id}, part_id={self.part_id}, name='{self.name}')>"


class StockTestResult(Base, IdMixin, TimestampMixin):
    """Test result for a specific stock item.

    Records the outcome of a test performed on inventory.
    """

    inventory_record_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_template.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Link to predefined test template"
    )
    test_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Test name (from template or custom)"
    )
    result: Mapped[TestResult] = mapped_column(
        String(20), nullable=False, default=TestResult.PENDING
    )
    value: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Test value (numeric or text result)"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    inventory_record: Mapped["InventoryRecord"] = relationship(
        "InventoryRecord", back_populates="test_results"
    )
    template: Mapped["TestTemplate | None"] = relationship(
        "TestTemplate", back_populates="test_results"
    )
    tested_by_user: Mapped["User | None"] = relationship(
        "User", back_populates="test_results"
    )

    def __repr__(self) -> str:
        return f"<StockTestResult(id={self.id}, inv_id={self.inventory_record_id}, test='{self.test_name}', result={self.result})>"


class TransferStatus(str, Enum):
    """Status of a stock transfer."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StockTransfer(Base, IdMixin, TimestampMixin):
    """Record of stock being transferred between locations.

    Tracks the movement of inventory from one location to another.
    """

    source_inventory_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Source inventory record (may be null if source deleted)"
    )
    target_inventory_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_record.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="Target inventory record (created on transfer)"
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("part.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(precision=15, scale=4), nullable=False, comment="Quantity transferred"
    )
    source_location: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Original location"
    )
    target_location: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Destination location"
    )
    source_lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[TransferStatus] = mapped_column(
        String(20), nullable=False, default=TransferStatus.COMPLETED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    transferred_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    transferred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    source_inventory: Mapped["InventoryRecord | None"] = relationship(
        "InventoryRecord", foreign_keys=[source_inventory_id], backref="outgoing_transfers"
    )
    target_inventory: Mapped["InventoryRecord | None"] = relationship(
        "InventoryRecord", foreign_keys=[target_inventory_id], backref="incoming_transfers"
    )
    part: Mapped["Part"] = relationship("Part", backref="stock_transfers")
    transferred_by_user: Mapped["User | None"] = relationship(
        "User", backref="stock_transfers"
    )

    def __repr__(self) -> str:
        return f"<StockTransfer(id={self.id}, part_id={self.part_id}, qty={self.quantity}, {self.source_location} -> {self.target_location})>"
