"""Inventory utility functions including OPAL number generation."""

from sqlalchemy.orm import Session

from opal.db.models.inventory import InventoryRecord

# Re-export from new designators module for backward compatibility
from opal.core.designators import generate_opal_number  # noqa: F401


def get_inventory_by_opal(db: Session, opal_number: str) -> InventoryRecord | None:
    """Look up an inventory record by its OPAL number.

    Args:
        db: Database session
        opal_number: The OPAL number (e.g., "OPAL-00042")

    Returns:
        The InventoryRecord if found, None otherwise.
    """
    return db.query(InventoryRecord).filter(
        InventoryRecord.opal_number == opal_number
    ).first()
