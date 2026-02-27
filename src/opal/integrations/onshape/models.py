"""Pydantic models for Onshape API responses."""

from typing import Any

from pydantic import BaseModel, Field


class OnshapePart(BaseModel):
    """A part as returned by Onshape's parts API."""

    part_id: str = Field(description="Onshape part ID within the element")
    name: str = Field(description="Part name in Onshape")
    part_number: str | None = Field(default=None, description="Part number in Onshape (if set)")
    description: str | None = Field(default=None, description="Part description")
    revision: str | None = Field(default=None, description="Part revision")
    material: str | None = Field(default=None, description="Material name")
    state: str | None = Field(default=None, description="Release state")
    appearance: dict | None = Field(default=None, description="Visual appearance data")


class OnshapeBOMItem(BaseModel):
    """A single row in an Onshape BOM."""

    item_source: dict = Field(description="Source reference (document, element, part)")
    source_element_id: str = Field(default="", description="Source Part Studio element ID")
    part_id: str = Field(default="", description="Onshape part ID")
    part_name: str = Field(default="", description="Part name")
    part_number: str | None = Field(default=None, description="Part number")
    description: str | None = Field(default=None, description="Part description")
    quantity: int = Field(default=1, description="Quantity in parent assembly")
    is_standard_content: bool = Field(default=False, description="Whether this is standard content")
    children: list["OnshapeBOMItem"] = Field(default_factory=list, description="Sub-components")


class BOMParseWarning(BaseModel):
    """Diagnostic warning generated during BOM parsing."""

    item_index: int
    field: str
    message: str
    raw_value: Any = None


class OnshapeBOM(BaseModel):
    """Top-level BOM response from Onshape."""

    document_id: str
    element_id: str
    items: list[OnshapeBOMItem] = Field(default_factory=list)
    warnings: list[BOMParseWarning] = Field(default_factory=list)
    header_map: dict[str, str] = Field(default_factory=dict)


class OnshapeDocument(BaseModel):
    """Onshape document metadata."""

    id: str
    name: str
    owner: str | None = None
    default_workspace_id: str | None = None


class OnshapeMetadataProperty(BaseModel):
    """A single metadata property on an Onshape part."""

    name: str
    value: str | None = None
    property_id: str | None = None


class OnshapeElement(BaseModel):
    """An element (tab) within an Onshape document."""

    id: str
    name: str
    element_type: str  # "PARTSTUDIO", "ASSEMBLY", "BLOB", etc.
