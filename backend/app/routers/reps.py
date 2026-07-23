from fastapi import APIRouter, Query, Response

from app.salesforce import client
from app.sheets import client as sheets_client

router = APIRouter()


@router.get("/reps")
def list_reps() -> dict:
    """Active sales representatives (Account.Salesperson__c picklist), sorted."""
    return {"reps": client.list_reps()}


@router.get("/territories")
def list_territories() -> dict:
    """Distinct Account.SalesTerritory__c values ("Midwest - Aviva Landin", ...)."""
    return {"territories": client.list_territories()}


@router.get("/order-writers")
def list_order_writers() -> dict:
    """Who can be credited with writing an order (Written_By__c picklist)."""
    return {"writers": client.list_order_writers()}


@router.get("/territory")
def territory_for_state(
    response: Response, state: str = Query(..., min_length=2, max_length=2)
) -> dict:
    """Sales territory for a 2-letter US state code (region/rep sheet).

    Used to auto-assign a territory to a new account from its Ship To state;
    `territory` is null when the state isn't mapped.
    """
    # Live sheet lookup — don't let the browser cache a mapping that just changed.
    response.headers["Cache-Control"] = "no-store"
    return {"territory": sheets_client.territory_for_state(state)}
