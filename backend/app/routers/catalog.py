"""/api/admin/catalog -- which style+colors the order form offers.

Admin-only. The list is the same catalogue /api/products serves; the only thing
stored on this side is the hidden set (app/services/hidden_products.py), one row
per (season, style, color). Salesforce is never written to.
"""
import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.security import AdminRequired
from app.db.session import get_db
from app.routers.products import load_rows
from app.salesforce import mapping
from app.services import hidden_products

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", dependencies=[AdminRequired])

SEASON = Field(pattern=r"^[FS]\d{2}$")


class HiddenRequest(BaseModel):
    season_code: str = SEASON
    style_name: str = Field(min_length=1)
    color: str = Field(min_length=1)
    hidden: bool


@router.get("/catalog")
def get_catalog(
    season: str = Query(..., pattern=r"^[FS]\d{2}$"),
    db: Session = Depends(get_db),
) -> dict:
    """Every style+color in the season, each flagged `hidden`.

    Identical to /api/products by design: what the admin ticks here has to be
    the same list the buyer sees, or the two drift and the checkbox stops
    meaning anything.
    """
    rows = hidden_products.flag_rows(
        load_rows(season), hidden_products.hidden_keys(db, season)
    )
    return {
        "season": season,
        "label": mapping.season_label(season),
        "rows": rows,
        "hiddenCount": sum(1 for r in rows if r["hidden"]),
    }


@router.post("/catalog/hidden")
def set_catalog_hidden(payload: HiddenRequest, db: Session = Depends(get_db)) -> dict:
    """Hide or show one style+color. One row at a time, not a whole-list save:
    two admins with the tab open would otherwise overwrite each other's ticks
    with whatever their page happened to be showing."""
    state = hidden_products.set_hidden(
        db, payload.season_code, payload.style_name, payload.color, payload.hidden
    )
    return {
        "seasonCode": payload.season_code,
        "styleName": payload.style_name,
        "color": payload.color,
        "hidden": state,
    }
