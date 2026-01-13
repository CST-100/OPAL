"""Project configuration loading and management."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TierConfig(BaseModel):
    """Inventory tier configuration."""

    level: int
    name: str
    code: str
    description: str = ""


class PartNumberingConfig(BaseModel):
    """Part numbering format configuration."""

    prefix: str = ""
    separator: str = "-"
    sequence_digits: int = 4
    format: str = "{prefix}{sep}{tier_code}{sep}{sequence}"


class RequirementConfig(BaseModel):
    """Project-level requirement definition."""

    id: str  # e.g., "REQ-001"
    title: str
    description: str = ""
    category: str = ""


# Default tier presets
DEFAULT_TIERS = [
    TierConfig(
        level=1,
        name="Flight",
        code="F",
        description="Flight-critical hardware requiring full traceability",
    ),
    TierConfig(
        level=2,
        name="Ground",
        code="G",
        description="Ground support equipment",
    ),
    TierConfig(
        level=3,
        name="Loose",
        code="L",
        description="Consumables and non-critical items",
    ),
]


class ProjectConfig(BaseModel):
    """Project configuration loaded from opal.project.yaml."""

    name: str
    description: str = ""
    tiers: list[TierConfig] = Field(default_factory=lambda: list(DEFAULT_TIERS))
    part_numbering: PartNumberingConfig = Field(default_factory=PartNumberingConfig)
    requirements: list[RequirementConfig] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    cad_directories: list[str] = Field(default_factory=list)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    # Set after loading - the directory containing the config file
    project_dir: Path | None = None

    @property
    def database_path(self) -> Path:
        """Get the database path for this project."""
        if self.project_dir:
            return self.project_dir / "opal.db"
        return Path("./data/opal.db")

    @property
    def database_url(self) -> str:
        """Get the SQLAlchemy database URL for this project."""
        return f"sqlite:///{self.database_path}"

    @property
    def attachments_dir(self) -> Path:
        """Get the attachments directory for this project."""
        if self.project_dir:
            return self.project_dir / "attachments"
        return Path("./data/attachments")

    def get_tier(self, level: int) -> TierConfig | None:
        """Get a tier by level number."""
        for tier in self.tiers:
            if tier.level == level:
                return tier
        return None

    def get_tier_by_code(self, code: str) -> TierConfig | None:
        """Get a tier by its code (e.g., 'F' for Flight)."""
        for tier in self.tiers:
            if tier.code == code:
                return tier
        return None

    def get_requirement(self, req_id: str) -> RequirementConfig | None:
        """Get a requirement by its ID."""
        for req in self.requirements:
            if req.id == req_id:
                return req
        return None

    def generate_part_number(self, tier_level: int, sequence: int) -> str:
        """Generate a part number according to project config.

        Args:
            tier_level: The tier level (1, 2, 3, etc.)
            sequence: The sequence number for this part.

        Returns:
            Formatted part number string.

        Raises:
            ValueError: If tier level doesn't exist.
        """
        tier = self.get_tier(tier_level)
        if not tier:
            raise ValueError(f"Unknown tier level: {tier_level}")

        return self.part_numbering.format.format(
            prefix=self.part_numbering.prefix,
            sep=self.part_numbering.separator,
            tier_code=tier.code,
            tier_name=tier.name,
            tier_level=tier.level,
            sequence=str(sequence).zfill(self.part_numbering.sequence_digits),
        )


# Project config filename
PROJECT_CONFIG_FILENAME = "opal.project.yaml"


def find_project_config(start_dir: Path | None = None) -> Path | None:
    """Find opal.project.yaml in the given directory or any parent.

    Args:
        start_dir: Directory to start searching from. Defaults to cwd.

    Returns:
        Path to the config file if found, None otherwise.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Search up to filesystem root
    while current != current.parent:
        config_path = current / PROJECT_CONFIG_FILENAME
        if config_path.exists():
            return config_path
        current = current.parent

    # Check root directory too
    config_path = current / PROJECT_CONFIG_FILENAME
    if config_path.exists():
        return config_path

    return None


def load_project_config(config_path: Path) -> ProjectConfig:
    """Load project configuration from a YAML file.

    Args:
        config_path: Path to the opal.project.yaml file.

    Returns:
        Parsed ProjectConfig object.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        ValueError: If the config file is invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Project config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    try:
        config = ProjectConfig(**data)
        config.project_dir = config_path.parent.resolve()
        return config
    except Exception as e:
        raise ValueError(f"Invalid project config: {e}") from e


def get_project_config(project_path: Path | None = None) -> ProjectConfig | None:
    """Get project configuration, auto-detecting if not specified.

    Args:
        project_path: Explicit path to project directory or config file.
                     If None, searches for config in cwd and parents.

    Returns:
        ProjectConfig if found/specified, None otherwise.
    """
    if project_path is not None:
        project_path = Path(project_path).resolve()

        # If it's a directory, look for config file inside
        if project_path.is_dir():
            config_path = project_path / PROJECT_CONFIG_FILENAME
        else:
            config_path = project_path

        if config_path.exists():
            return load_project_config(config_path)
        else:
            # No config file, but treat as project directory anyway
            config = ProjectConfig(name=project_path.name)
            config.project_dir = project_path if project_path.is_dir() else project_path.parent
            return config

    # Auto-detect from current directory
    config_path = find_project_config()
    if config_path:
        return load_project_config(config_path)

    return None


def create_project_config(
    project_dir: Path,
    name: str,
    description: str = "",
    prefix: str = "",
    separator: str = "-",
    sequence_digits: int = 4,
    part_number_format: str = "{prefix}{sep}{tier_code}{sep}{sequence}",
    tiers: list[TierConfig] | None = None,
    requirements: list[RequirementConfig] | None = None,
    categories: list[str] | None = None,
    cad_directories: list[str] | None = None,
) -> ProjectConfig:
    """Create a new project configuration file.

    Args:
        project_dir: Directory to create the project in.
        name: Project name.
        description: Project description.
        prefix: Part number prefix.
        separator: Part number separator (default: "-").
        sequence_digits: Number of digits in sequence (default: 4).
        part_number_format: Format string for part numbers.
        tiers: List of inventory tiers (defaults to Flight/Ground/Loose).
        requirements: List of project requirements.
        categories: List of part categories.
        cad_directories: List of CAD file directories.

    Returns:
        The created ProjectConfig.
    """
    project_dir = Path(project_dir).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    config = ProjectConfig(
        name=name,
        description=description,
        tiers=tiers if tiers is not None else list(DEFAULT_TIERS),
        part_numbering=PartNumberingConfig(
            prefix=prefix,
            separator=separator,
            sequence_digits=sequence_digits,
            format=part_number_format,
        ),
        requirements=requirements or [],
        categories=categories or [],
        cad_directories=cad_directories or [],
    )
    config.project_dir = project_dir

    # Write config file
    save_project_config(config)

    return config


def save_project_config(config: ProjectConfig) -> None:
    """Save project configuration to its YAML file.

    Args:
        config: The ProjectConfig to save.

    Raises:
        ValueError: If project_dir is not set.
    """
    if not config.project_dir:
        raise ValueError("Cannot save config without project_dir set")

    config_path = config.project_dir / PROJECT_CONFIG_FILENAME
    config_data = {
        "name": config.name,
        "description": config.description,
        "tiers": [
            {
                "level": t.level,
                "name": t.name,
                "code": t.code,
                "description": t.description,
            }
            for t in config.tiers
        ],
        "part_numbering": {
            "prefix": config.part_numbering.prefix,
            "separator": config.part_numbering.separator,
            "sequence_digits": config.part_numbering.sequence_digits,
            "format": config.part_numbering.format,
        },
        "requirements": [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "category": r.category,
            }
            for r in config.requirements
        ],
        "categories": config.categories,
        "cad_directories": config.cad_directories,
    }

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
