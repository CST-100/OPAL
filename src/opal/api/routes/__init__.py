"""API routes."""

from fastapi import APIRouter

from opal.api.routes import health, users

router = APIRouter()

# Include all route modules
router.include_router(health.router, tags=["health"])
router.include_router(users.router, prefix="/users", tags=["users"])

# TODO: Add more route modules as they are implemented
# router.include_router(parts.router, prefix="/parts", tags=["parts"])
# router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
# router.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
# router.include_router(procedures.router, prefix="/procedures", tags=["procedures"])
# router.include_router(execution.router, prefix="/procedure-instances", tags=["execution"])
# router.include_router(issues.router, prefix="/issues", tags=["issues"])
