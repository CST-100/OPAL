"""API routes."""

from fastapi import APIRouter

from opal.api.routes import (
    bom,
    datasets,
    events,
    execution,
    health,
    inventory,
    issues,
    parts,
    procedures,
    project,
    purchases,
    reports,
    requirements,
    risks,
    suppliers,
    users,
    workcenters,
)

router = APIRouter()

# Include all route modules
router.include_router(health.router, tags=["health"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(parts.router, prefix="/parts", tags=["parts"])
router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
router.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
router.include_router(procedures.router)  # Has its own /procedures prefix
router.include_router(execution.router)  # Has its own /procedure-instances prefix
router.include_router(issues.router)  # Has its own /issues prefix
router.include_router(risks.router)  # Has its own /risks prefix
router.include_router(datasets.router)  # Has its own /datasets prefix
router.include_router(workcenters.router)  # Has its own /workcenters prefix
router.include_router(suppliers.router)  # Has its own /suppliers prefix
router.include_router(events.router)  # Has its own /events prefix
router.include_router(reports.router)  # Has its own /reports prefix
router.include_router(requirements.router, prefix="/requirements", tags=["requirements"])
router.include_router(bom.router, prefix="/bom", tags=["bom"])
router.include_router(project.router)  # Has its own /project prefix
