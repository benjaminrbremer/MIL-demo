"""GET /v1/slides and GET /v1/slides/{id}: the slide registry (REQ-005, REQ-006).

The response model is the allowlist: only the fields declared on `Slide`
are ever serialized. `file_path` and `sha256` stay inside the device.
"""

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import db

router = APIRouter(prefix="/v1")


class SlideError(BaseModel):
    """Why a slide is unreadable."""

    code: str
    message: str


class Slide(BaseModel):
    """A slide as served by the API: allowlisted fields only."""

    id: str
    status: str
    width: int | None
    height: int | None
    level_count: int | None
    mpp_x: float | None
    mpp_y: float | None
    detected_at: str
    registered_at: str | None
    error: SlideError | None


def _to_slide(row: sqlite3.Row) -> Slide:
    """Map a database row to the API model, field by field."""
    # Explicit mapping rather than Slide(**row): a new column added to the
    # table later can't leak into responses by accident.
    error = None
    if row["error_code"] is not None:
        error = SlideError(code=row["error_code"], message=row["error_message"])
    return Slide(
        id=row["id"],
        status=row["status"],
        width=row["width"],
        height=row["height"],
        level_count=row["level_count"],
        mpp_x=row["mpp_x"],
        mpp_y=row["mpp_y"],
        detected_at=row["detected_at"],
        registered_at=row["registered_at"],
        error=error,
    )


@router.get("/slides")
def list_slides(request: Request) -> list[Slide]:
    """All slides on the device, most recently detected first."""
    # Plain `def`: sqlite3 calls block, so FastAPI runs this in a thread.
    return [_to_slide(row) for row in db.list_slides(request.app.state.db_path)]


# Roadmap item 4: register the `.dzi` and tile routes before this one, or
# "/v1/slides/<id>.dzi" will match here with slide_id="<id>.dzi".
@router.get("/slides/{slide_id}")
def get_slide(slide_id: str, request: Request) -> Slide:
    """One slide by ID; 404 NOT_FOUND if unknown."""
    row = db.get_slide(request.app.state.db_path, slide_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Slide not found")
    return _to_slide(row)
