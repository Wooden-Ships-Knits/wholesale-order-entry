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


@router.get("/split-options")
def list_split_options(response: Response) -> dict:
    """Names offerable in the order form's "Split with" dropdown (REGION col C).

    Deliberately not the Written_By__c picklist: a split is between reps, and
    that picklist also contains people who write orders for a rep. split_with
    is never pushed to Salesforce, so it need not match a Salesforce picklist.
    """
    response.headers["Cache-Control"] = "no-store"
    return {"options": sheets_client.split_options()}


@router.get("/writer-reps")
def list_writer_reps(response: Response) -> dict:
    """"Written By" name -> the rep they belong to (the sheet's 'Split' tab).

    Drives the order form's Split rule: the writer's rep is compared against the
    rep who owns the Sales Territory.
    """
    # Same reasoning as /territory: the sales team edits this sheet, and a
    # browser-cached copy would hide the edit for far longer than the 5-minute
    # server-side cache.
    response.headers["Cache-Control"] = "no-store"
    return {"writerReps": sheets_client.writer_rep_map()}


@router.get("/territory")
def territory_for_state(
    response: Response, state: str = Query(..., min_length=2, max_length=2)
) -> dict:
    """Sales territory for a 2-letter US state code (region/rep sheet).

    Used to auto-assign a territory to a new account from its Ship To state;
    `territory` is null when the state isn't mapped.

    `rep` is the owner of that territory (REGION column C). The order form uses
    it for the Split rule on every account — including existing ones, whose
    Salesforce territory label may name a showroom rather than a rep.
    """
    # Live sheet lookup — don't let the browser cache a mapping that just changed.
    response.headers["Cache-Control"] = "no-store"
    return {
        "territory": sheets_client.territory_for_state(state),
        "rep": sheets_client.territory_rep_for_state(state),
    }
