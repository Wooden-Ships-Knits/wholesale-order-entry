from fastapi import APIRouter

from app.salesforce import client

router = APIRouter()


@router.get("/reps")
def list_reps() -> dict:
    """Active sales representatives (Account.Salesperson__c picklist), sorted."""
    return {"reps": client.list_reps()}
