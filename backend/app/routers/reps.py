from fastapi import APIRouter

from app.salesforce import client

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
