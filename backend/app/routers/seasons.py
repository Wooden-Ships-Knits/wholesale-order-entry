from fastapi import APIRouter

from app.salesforce import client, mapping

router = APIRouter()


@router.get("/seasons")
def list_seasons() -> dict:
    """Available seasons = active '<season> Wholesale' price books, newest first."""
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
    return {"seasons": seasons[:2]}  # only return the two most recent seasons, 
#discuss with other team which seasons to sale at this current of time. 
