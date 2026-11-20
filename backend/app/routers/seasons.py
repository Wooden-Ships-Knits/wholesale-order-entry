from fastapi import APIRouter, Query

from app.salesforce import client, mapping
from app.services import form_seasons

router = APIRouter()


def all_seasons() -> list[dict]:
    """Every active '<season> Wholesale' price book as a season, newest first."""
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
    return seasons


@router.get("/seasons")
def list_seasons(limit: int | None = Query(None, ge=0, le=50)) -> dict:
    """Seasons with an active wholesale price book, newest first.

    No limit = what the order form sells: the 3 newest, minus any unticked in
    /admin -> Catalog (app/services/form_seasons.py). limit=0 = every season,
    which the admin tools need (payment-notice cards are built for past seasons
    too); limit=N = N newest.
    """
    seasons = all_seasons()
    if limit is None:
        cands = form_seasons.candidates(s["code"] for s in seasons)
        on = set(form_seasons.shown(cands, form_seasons.hidden_codes()))
        return {"seasons": [s for s in seasons if s["code"] in on]}
    return {"seasons": seasons if limit == 0 else seasons[:limit]}
