"""Welcome / onboarding API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from opal.api.deps import DbSession, RequiredUser
from opal.db.models import Part

router = APIRouter(prefix="/welcome", tags=["welcome"])


class WelcomeResponse(BaseModel):
    ok: bool = True


@router.post("/complete", response_model=WelcomeResponse)
async def complete_onboarding(
    db: DbSession,
    user: RequiredUser,
) -> WelcomeResponse:
    """Mark the current user's onboarding as complete."""
    user.needs_onboarding = False
    db.commit()
    return WelcomeResponse()


@router.post("/load-demo", response_model=WelcomeResponse)
async def load_demo_data(
    db: DbSession,
    user: RequiredUser,
) -> WelcomeResponse:
    """Load Project Kestrel demo data. Admin only, fresh DB only."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    if db.query(Part).first():
        raise HTTPException(status_code=400, detail="Database already has parts — cannot load demo data")

    from opal.seed import seed_database

    seed_database(db)
    user.needs_onboarding = False
    db.commit()
    return WelcomeResponse()
