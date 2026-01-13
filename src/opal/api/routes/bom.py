"""Bill of Materials (BOM) management endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from opal.api.deps import CurrentUserId, DbSession
from opal.core.audit import get_model_dict, log_create, log_update
from opal.db.models import BOMLine, Part

router = APIRouter()


class BOMLineCreate(BaseModel):
    """Schema for adding a component to an assembly."""

    component_id: int
    quantity: int = 1
    reference_designator: str | None = None
    notes: str | None = None


class BOMLineUpdate(BaseModel):
    """Schema for updating a BOM line."""

    quantity: int | None = None
    reference_designator: str | None = None
    notes: str | None = None


class BOMLineResponse(BaseModel):
    """Schema for BOM line response."""

    id: int
    assembly_id: int
    component_id: int
    component_name: str
    component_external_pn: str | None
    component_tier: int
    quantity: int
    reference_designator: str | None
    notes: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class BOMTreeNode(BaseModel):
    """Schema for a node in the BOM tree."""

    part_id: int
    name: str
    external_pn: str | None
    tier: int
    quantity: int = 1
    reference_designator: str | None = None
    children: list["BOMTreeNode"] = []


def get_bom_line_response(line: BOMLine) -> BOMLineResponse:
    """Convert BOMLine to response."""
    return BOMLineResponse(
        id=line.id,
        assembly_id=line.assembly_id,
        component_id=line.component_id,
        component_name=line.component.name,
        component_external_pn=line.component.external_pn,
        component_tier=line.component.tier,
        quantity=line.quantity,
        reference_designator=line.reference_designator,
        notes=line.notes,
        created_at=line.created_at.isoformat(),
        updated_at=line.updated_at.isoformat(),
    )


def build_bom_tree(db: DbSession, part: Part, quantity: int = 1, ref: str | None = None, visited: set | None = None) -> BOMTreeNode:
    """Recursively build BOM tree for a part."""
    if visited is None:
        visited = set()

    # Detect circular references
    if part.id in visited:
        return BOMTreeNode(
            part_id=part.id,
            name=f"{part.name} [CIRCULAR REF]",
            external_pn=part.external_pn,
            tier=part.tier,
            quantity=quantity,
            reference_designator=ref,
            children=[],
        )

    visited = visited | {part.id}

    children = []
    for line in part.bom_lines:
        child_node = build_bom_tree(db, line.component, line.quantity, line.reference_designator, visited)
        children.append(child_node)

    return BOMTreeNode(
        part_id=part.id,
        name=part.name,
        external_pn=part.external_pn,
        tier=part.tier,
        quantity=quantity,
        reference_designator=ref,
        children=children,
    )


@router.get("/assemblies/{assembly_id}", response_model=list[BOMLineResponse])
async def get_assembly_bom(
    db: DbSession,
    assembly_id: int,
) -> list[BOMLineResponse]:
    """Get the BOM (list of components) for an assembly."""
    part = db.query(Part).filter(Part.id == assembly_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {assembly_id} not found",
        )

    lines = db.query(BOMLine).filter(BOMLine.assembly_id == assembly_id).all()
    return [get_bom_line_response(line) for line in lines]


@router.get("/assemblies/{assembly_id}/tree", response_model=BOMTreeNode)
async def get_assembly_tree(
    db: DbSession,
    assembly_id: int,
) -> BOMTreeNode:
    """Get the full BOM tree for an assembly (recursive)."""
    part = db.query(Part).filter(Part.id == assembly_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {assembly_id} not found",
        )

    return build_bom_tree(db, part)


@router.get("/components/{component_id}/used-in", response_model=list[BOMLineResponse])
async def get_where_used(
    db: DbSession,
    component_id: int,
) -> list[BOMLineResponse]:
    """Get all assemblies that use a component (where-used)."""
    part = db.query(Part).filter(Part.id == component_id, Part.deleted_at.is_(None)).first()
    if not part:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Part {component_id} not found",
        )

    lines = db.query(BOMLine).filter(BOMLine.component_id == component_id).all()
    return [get_bom_line_response(line) for line in lines]


@router.post("/assemblies/{assembly_id}", response_model=BOMLineResponse, status_code=status.HTTP_201_CREATED)
async def add_component_to_assembly(
    db: DbSession,
    assembly_id: int,
    line_in: BOMLineCreate,
    user_id: CurrentUserId,
) -> BOMLineResponse:
    """Add a component to an assembly's BOM."""
    # Verify assembly exists
    assembly = db.query(Part).filter(Part.id == assembly_id, Part.deleted_at.is_(None)).first()
    if not assembly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assembly part {assembly_id} not found",
        )

    # Verify component exists
    component = db.query(Part).filter(Part.id == line_in.component_id, Part.deleted_at.is_(None)).first()
    if not component:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Component part {line_in.component_id} not found",
        )

    # Cannot add self as component
    if assembly_id == line_in.component_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A part cannot be a component of itself",
        )

    # Check for existing line
    existing = (
        db.query(BOMLine)
        .filter(BOMLine.assembly_id == assembly_id, BOMLine.component_id == line_in.component_id)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Component {line_in.component_id} is already in assembly {assembly_id} BOM",
        )

    line = BOMLine(
        assembly_id=assembly_id,
        component_id=line_in.component_id,
        quantity=line_in.quantity,
        reference_designator=line_in.reference_designator,
        notes=line_in.notes,
    )
    db.add(line)
    db.commit()
    db.refresh(line)

    log_create(db, line, user_id)
    db.commit()

    return get_bom_line_response(line)


@router.patch("/{line_id}", response_model=BOMLineResponse)
async def update_bom_line(
    db: DbSession,
    line_id: int,
    line_in: BOMLineUpdate,
    user_id: CurrentUserId,
) -> BOMLineResponse:
    """Update a BOM line."""
    line = db.query(BOMLine).filter(BOMLine.id == line_id).first()
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BOM line {line_id} not found",
        )

    old_values = get_model_dict(line)

    if line_in.quantity is not None:
        if line_in.quantity < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be at least 1",
            )
        line.quantity = line_in.quantity

    if line_in.reference_designator is not None:
        line.reference_designator = line_in.reference_designator

    if line_in.notes is not None:
        line.notes = line_in.notes

    db.commit()
    db.refresh(line)

    log_update(db, line, old_values, user_id)
    db.commit()

    return get_bom_line_response(line)


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_component_from_assembly(
    db: DbSession,
    line_id: int,
    user_id: CurrentUserId,
) -> None:
    """Remove a component from an assembly's BOM."""
    line = db.query(BOMLine).filter(BOMLine.id == line_id).first()
    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BOM line {line_id} not found",
        )

    db.delete(line)
    db.commit()
