"""Genealogy tracking utilities for assembly traceability.

Provides functions to:
- Record which components went into an assembly
- Query an assembly's component tree
- Query which assemblies contain a specific component
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from opal.db.models.genealogy import AssemblyComponent
from opal.db.models.inventory import (
    InventoryConsumption,
    InventoryProduction,
    InventoryRecord,
)


def record_assembly_genealogy(
    db: Session,
    production_id: int,
    consumption_ids: list[int],
) -> list[AssemblyComponent]:
    """Record the genealogy for a produced assembly.

    Links the production record to all the consumption records
    that were used to build it.

    Args:
        db: Database session
        production_id: ID of the InventoryProduction record (the assembly)
        consumption_ids: List of InventoryConsumption IDs (components used)

    Returns:
        List of created AssemblyComponent records
    """
    production = db.query(InventoryProduction).filter(
        InventoryProduction.id == production_id
    ).first()

    if not production:
        raise ValueError(f"Production record {production_id} not found")

    components = []
    for consumption_id in consumption_ids:
        consumption = db.query(InventoryConsumption).filter(
            InventoryConsumption.id == consumption_id
        ).first()

        if not consumption:
            continue

        # Get the OPAL number from the consumed inventory record
        inventory = db.query(InventoryRecord).filter(
            InventoryRecord.id == consumption.inventory_record_id
        ).first()

        opal_number = inventory.opal_number if inventory else None

        if opal_number:
            component = AssemblyComponent(
                production_id=production_id,
                consumption_id=consumption_id,
                component_opal_number=opal_number,
                quantity_used=consumption.quantity,
            )
            db.add(component)
            components.append(component)

    db.flush()
    return components


def get_assembly_components(
    db: Session,
    assembly_opal: str,
) -> list[dict]:
    """Get all components that make up an assembly.

    Args:
        db: Database session
        assembly_opal: OPAL number of the assembly (e.g., "OPAL-00100")

    Returns:
        List of component details including OPAL numbers and quantities
    """
    # Find productions that created this OPAL number
    productions = db.query(InventoryProduction).filter(
        InventoryProduction.produced_opal_number == assembly_opal
    ).all()

    if not productions:
        # Also check if the inventory record with this OPAL was created via production
        inventory = db.query(InventoryRecord).filter(
            InventoryRecord.opal_number == assembly_opal
        ).first()
        if inventory and inventory.source_production_id:
            productions = db.query(InventoryProduction).filter(
                InventoryProduction.id == inventory.source_production_id
            ).all()

    components = []
    for production in productions:
        for ac in production.assembly_components:
            # Get component details
            consumption = ac.consumption
            inventory = consumption.inventory_record if consumption else None
            part = inventory.part if inventory else None

            components.append({
                "component_opal_number": ac.component_opal_number,
                "quantity_used": float(ac.quantity_used),
                "part_id": part.id if part else None,
                "part_number": part.part_number if part else None,
                "part_name": part.name if part else None,
                "consumption_id": ac.consumption_id,
                "consumed_at": consumption.created_at.isoformat() if consumption else None,
            })

    return components


def get_assemblies_containing(
    db: Session,
    component_opal: str,
) -> list[dict]:
    """Get all assemblies that contain a specific component.

    Args:
        db: Database session
        component_opal: OPAL number of the component (e.g., "OPAL-00042")

    Returns:
        List of assembly details including OPAL numbers and work order info
    """
    # Find all assembly_component records for this OPAL number
    assembly_components = db.query(AssemblyComponent).filter(
        AssemblyComponent.component_opal_number == component_opal
    ).all()

    assemblies = []
    seen_opals = set()

    for ac in assembly_components:
        production = ac.production
        if not production:
            continue

        assembly_opal = production.produced_opal_number
        if not assembly_opal or assembly_opal in seen_opals:
            continue

        seen_opals.add(assembly_opal)

        # Get assembly details
        inventory = production.inventory_record
        part = inventory.part if inventory else None
        instance = production.procedure_instance

        assemblies.append({
            "assembly_opal_number": assembly_opal,
            "quantity_used": float(ac.quantity_used),
            "part_id": part.id if part else None,
            "part_number": part.part_number if part else None,
            "part_name": part.name if part else None,
            "work_order_number": instance.work_order_number if instance else None,
            "produced_at": production.created_at.isoformat(),
        })

    return assemblies


def get_full_genealogy(
    db: Session,
    opal_number: str,
) -> dict:
    """Get complete genealogy for an OPAL number.

    Returns both components (if assembly) and assemblies containing it.

    Args:
        db: Database session
        opal_number: OPAL number to query

    Returns:
        Dict with 'components' and 'assemblies_containing' lists
    """
    return {
        "opal_number": opal_number,
        "components": get_assembly_components(db, opal_number),
        "assemblies_containing": get_assemblies_containing(db, opal_number),
    }
