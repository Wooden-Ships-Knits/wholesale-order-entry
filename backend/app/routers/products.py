import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.salesforce import client, mapping
from app.services import hidden_products

logger = logging.getLogger(__name__)

router = APIRouter()


def load_rows(season: str) -> list[dict]:
    """The season's price book, grouped by style + color, straight from
    Salesforce. No visibility flag -- /api/admin/catalog needs the unfiltered
    list to choose from, and get_products() adds the flag below."""
    books = {
        mapping.season_from_pricebook_name(b["Name"]): b
        for b in client.list_wholesale_pricebooks()
    }
    book = books.get(season)
    if book is None:
        raise HTTPException(status_code=404, detail=f"No wholesale price book for season {season}")

    entries = client.get_pricebook_entries(book["Id"])
    rows, stats = mapping.group_products(entries)
    if stats["unparsed_name"] or stats["price_conflicts"]:
        logger.warning("Product mapping stats for %s: %s", season, stats)
    return rows


@router.get("/products")
def get_products(
    season: str = Query(..., pattern=r"^[FS]\d{2}$"),
    db: Session = Depends(get_db),
) -> dict:
    """Product rows (grouped by style + color, sizes pivoted) for one season.

    Rows the admin has hidden come back with "hidden": true rather than being
    dropped -- see app/services/hidden_products.py for why removing them would
    break orders already out for signature.
    """
    rows = hidden_products.flag_rows(
        load_rows(season), hidden_products.hidden_keys(db, season)
    )
    return {"season": season, "label": mapping.season_label(season), "rows": rows}
