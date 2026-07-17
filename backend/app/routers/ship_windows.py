from fastapi import APIRouter, Query

from app.sheets import client

router = APIRouter()


@router.get("/ship-windows")
def list_ship_windows(season: str = Query(..., pattern=r"^[FS]\d{2}$")) -> dict:
    """Ship windows offered for a season, read live from the planning sheet."""
    return {"shipWindows": client.list_ship_windows(season)}
