import logging

from fastapi import APIRouter, HTTPException, Query

from app.salesforce import client, mapping

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/products")
def get_products(season: str = Query(..., pattern=r"^[FS]\d{2}$")) -> dict:
    """Product rows (grouped by style + color, sizes pivoted) for one season."""
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
    return {"season": season, "label": mapping.season_label(season), "rows": rows}
