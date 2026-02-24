"""Onshape integration for bidirectional BOM and metadata sync.

This integration is OFF by default. It only activates when:
1. OPAL_ONSHAPE_ACCESS_KEY and OPAL_ONSHAPE_SECRET_KEY env vars are set
2. At least one Onshape document is registered in opal.project.yaml
"""

from opal.integrations.onshape.client import OnshapeClient
from opal.integrations.onshape.models import OnshapeBOM, OnshapeBOMItem, OnshapePart

__all__ = [
    "OnshapeBOM",
    "OnshapeBOMItem",
    "OnshapeClient",
    "OnshapePart",
    "is_enabled",
]


def is_enabled() -> bool:
    """Check if Onshape integration is enabled (credentials configured)."""
    from opal.config import get_active_settings

    settings = get_active_settings()
    return settings.onshape_enabled
