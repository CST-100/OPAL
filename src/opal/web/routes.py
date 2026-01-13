"""Web UI routes."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from opal.api.deps import DbSession
from opal.db.models import User

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: DbSession) -> HTMLResponse:
    """Home page."""
    # Get all users for the user selector
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "users": users,
            "title": "OPAL",
        },
    )


@router.get("/parts", response_class=HTMLResponse)
async def parts_list(request: Request, db: DbSession) -> HTMLResponse:
    """Parts list page."""
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712

    return templates.TemplateResponse(
        "parts/list.html",
        {
            "request": request,
            "users": users,
            "title": "Parts - OPAL",
        },
    )


@router.get("/procedures", response_class=HTMLResponse)
async def procedures_list(request: Request, db: DbSession) -> HTMLResponse:
    """Procedures list page."""
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712

    return templates.TemplateResponse(
        "procedures/list.html",
        {
            "request": request,
            "users": users,
            "title": "Procedures - OPAL",
        },
    )


@router.get("/issues", response_class=HTMLResponse)
async def issues_list(request: Request, db: DbSession) -> HTMLResponse:
    """Issues list page."""
    users = db.query(User).filter(User.is_active == True).all()  # noqa: E712

    return templates.TemplateResponse(
        "issues/list.html",
        {
            "request": request,
            "users": users,
            "title": "Issues - OPAL",
        },
    )
