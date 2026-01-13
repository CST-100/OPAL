"""Project configuration API routes."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from opal.config import get_active_project
from opal.project import (
    PartNumberingConfig,
    ProjectConfig,
    RequirementConfig,
    TierConfig,
    create_project_config,
    save_project_config,
)

router = APIRouter(prefix="/project", tags=["project"])


class TierInput(BaseModel):
    """Tier configuration input."""

    level: int
    name: str
    code: str
    description: str = ""


class PartNumberingInput(BaseModel):
    """Part numbering configuration input."""

    prefix: str = ""
    separator: str = "-"
    sequence_digits: int = 4
    format: str = "{prefix}{sep}{tier_code}{sep}{sequence}"


class RequirementInput(BaseModel):
    """Requirement configuration input."""

    id: str
    title: str
    description: str = ""
    category: str = ""


class ProjectConfigCreate(BaseModel):
    """Request model for creating a new project."""

    name: str
    description: str = ""
    directory: str
    tiers: list[TierInput]
    part_numbering: PartNumberingInput
    categories: list[str] = []
    requirements: list[RequirementInput] = []


class ProjectConfigUpdate(BaseModel):
    """Request model for updating project configuration."""

    name: str
    description: str = ""
    tiers: list[TierInput]
    part_numbering: PartNumberingInput
    categories: list[str] = []
    requirements: list[RequirementInput] = []


class ProjectConfigResponse(BaseModel):
    """Response model for project configuration."""

    name: str
    description: str
    project_dir: str | None
    tiers: list[TierInput]
    part_numbering: PartNumberingInput
    categories: list[str]
    requirements: list[RequirementInput]

    @classmethod
    def from_config(cls, config: ProjectConfig) -> "ProjectConfigResponse":
        """Create response from ProjectConfig."""
        return cls(
            name=config.name,
            description=config.description,
            project_dir=str(config.project_dir) if config.project_dir else None,
            tiers=[
                TierInput(
                    level=t.level,
                    name=t.name,
                    code=t.code,
                    description=t.description,
                )
                for t in config.tiers
            ],
            part_numbering=PartNumberingInput(
                prefix=config.part_numbering.prefix,
                separator=config.part_numbering.separator,
                sequence_digits=config.part_numbering.sequence_digits,
                format=config.part_numbering.format,
            ),
            categories=config.categories,
            requirements=[
                RequirementInput(
                    id=r.id,
                    title=r.title,
                    description=r.description,
                    category=r.category,
                )
                for r in config.requirements
            ],
        )


@router.get("/config")
async def get_project_config() -> ProjectConfigResponse:
    """Get current project configuration."""
    project = get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project configuration")
    return ProjectConfigResponse.from_config(project)


@router.post("/config")
async def create_project(data: ProjectConfigCreate) -> ProjectConfigResponse:
    """Create a new project configuration."""
    directory = Path(data.directory).resolve()

    # Check if config already exists
    config_path = directory / "opal.project.yaml"
    if config_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Project configuration already exists at {config_path}",
        )

    # Convert input tiers to TierConfig
    tiers = [
        TierConfig(
            level=t.level,
            name=t.name,
            code=t.code,
            description=t.description,
        )
        for t in data.tiers
    ]

    # Convert input requirements to RequirementConfig
    requirements = [
        RequirementConfig(
            id=r.id,
            title=r.title,
            description=r.description,
            category=r.category,
        )
        for r in data.requirements
    ]

    # Create project
    config = create_project_config(
        project_dir=directory,
        name=data.name,
        description=data.description,
        prefix=data.part_numbering.prefix,
        separator=data.part_numbering.separator,
        sequence_digits=data.part_numbering.sequence_digits,
        part_number_format=data.part_numbering.format,
        tiers=tiers,
        requirements=requirements,
        categories=data.categories,
    )

    return ProjectConfigResponse.from_config(config)


@router.put("/config")
async def update_project_config(data: ProjectConfigUpdate) -> ProjectConfigResponse:
    """Update existing project configuration."""
    project = get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project configuration")

    if not project.project_dir:
        raise HTTPException(
            status_code=400, detail="Cannot update project without project_dir"
        )

    # Update configuration
    project.name = data.name
    project.description = data.description

    # Update tiers
    project.tiers = [
        TierConfig(
            level=t.level,
            name=t.name,
            code=t.code,
            description=t.description,
        )
        for t in data.tiers
    ]

    # Update part numbering
    project.part_numbering = PartNumberingConfig(
        prefix=data.part_numbering.prefix,
        separator=data.part_numbering.separator,
        sequence_digits=data.part_numbering.sequence_digits,
        format=data.part_numbering.format,
    )

    # Update categories
    project.categories = data.categories

    # Update requirements
    project.requirements = [
        RequirementConfig(
            id=r.id,
            title=r.title,
            description=r.description,
            category=r.category,
        )
        for r in data.requirements
    ]

    # Save to file
    save_project_config(project)

    return ProjectConfigResponse.from_config(project)


class PartNumberPreview(BaseModel):
    """Part number preview request."""

    tier_level: int
    sequence: int = 1


class PartNumberPreviewResponse(BaseModel):
    """Part number preview response."""

    part_number: str
    tier_name: str


@router.post("/preview-part-number")
async def preview_part_number(data: PartNumberPreview) -> PartNumberPreviewResponse:
    """Preview what a part number would look like."""
    project = get_active_project()
    if not project:
        raise HTTPException(status_code=404, detail="No active project configuration")

    tier = project.get_tier(data.tier_level)
    if not tier:
        raise HTTPException(
            status_code=400, detail=f"Unknown tier level: {data.tier_level}"
        )

    part_number = project.generate_part_number(data.tier_level, data.sequence)

    return PartNumberPreviewResponse(part_number=part_number, tier_name=tier.name)
