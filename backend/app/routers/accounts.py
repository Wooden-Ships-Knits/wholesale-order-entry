from fastapi import APIRouter, HTTPException, Query

from app.salesforce import client, mapping

router = APIRouter()


@router.get("/accounts")
def lookup_accounts(
    email: str | None = Query(None, min_length=3, max_length=254),
    accountId: str | None = Query(None, min_length=15, max_length=18, pattern=r"^[a-zA-Z0-9]+$"),
) -> dict:
    """Buyer lookup by email or Salesforce account id. Returns all candidates
    so the frontend can show a matching-account dropdown."""
    if not email and not accountId:
        raise HTTPException(status_code=400, detail="Provide email or accountId")
    records = client.find_accounts(email=email, account_id=accountId)
    return {"matches": [mapping.map_account(r) for r in records]}
