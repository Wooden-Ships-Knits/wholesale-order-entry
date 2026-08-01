from fastapi import APIRouter, Query

from app.salesforce import client, mapping

router = APIRouter()


@router.get("/seasons")
def list_seasons(limit: int = Query(2, ge=0, le=50)) -> dict:
    """Available seasons = active '<season> Wholesale' price books, newest first.

    limit defaults to 2 because the order form should only sell the current and
    next season (interim decision 2026-07-16 — confirm with the team). Pass
    limit=0 for every season, which the admin tools need: payment-notice cards
    are built for past seasons too.
    """
    seasons = []
    for book in client.list_wholesale_pricebooks():
        code = mapping.season_from_pricebook_name(book["Name"])
        if code:
            seasons.append(
                {
                    "code": code,
                    "label": mapping.season_label(code),
                    "pricebookId": book["Id"],
                }
            )
    seasons.sort(key=lambda s: mapping.season_sort_key(s["code"]), reverse=True)
    return {"seasons": seasons if limit == 0 else seasons[:limit]} 
