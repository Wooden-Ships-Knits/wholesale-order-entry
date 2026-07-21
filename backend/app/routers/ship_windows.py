from fastapi import APIRouter, Query, Response

from app.sheets import client

router = APIRouter()


@router.get("/ship-windows")
def list_ship_windows(
    response: Response, season: str = Query(..., pattern=r"^[FS]\d{2}$")
) -> dict:
    """Ship windows offered for a season, read live from the planning sheet."""
    # Never let the browser reuse a stale list — a struck (sold-out) window must
    # disappear as soon as the short server cache refreshes.
    response.headers["Cache-Control"] = "no-store"
    return {"shipWindows": client.list_ship_windows(season)}
