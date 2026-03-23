"""Scan / OPALcode decode API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from opal.api.deps import DbSession
from opal.core.mri import decode_mri

router = APIRouter(prefix="/scan", tags=["scan"])


class ScanResponse(BaseModel):
    """Decoded OPALcode result."""

    type: str
    id: int | None = None
    label: str
    sublabel: str = ""
    found: bool = True


@router.get("/{code:path}", response_model=ScanResponse)
async def scan_code(
    code: str,
    db: DbSession,
) -> ScanResponse:
    """Decode an OPALcode and return the resolved entity.

    Accepts the full MRI string (e.g., OPAL:I:KST-F-0002/001).
    The code may be URL-encoded (slashes as %2F).
    """
    result = decode_mri(db, code)
    if result is None:
        raise HTTPException(status_code=400, detail=f"Invalid OPALcode format: {code}")

    return ScanResponse(
        type=result.type,
        id=result.id,
        label=result.label,
        sublabel=result.sublabel,
        found=result.id is not None,
    )
