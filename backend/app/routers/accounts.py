from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.geo import conflict
from app.salesforce import client, mapping

router = APIRouter()


@router.get("/accounts/nearby")
def nearby_accounts(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    k: int = Query(5, ge=1, le=25),
    maxMinutes: int | None = Query(None, ge=1, le=240),
) -> dict:
    """New-customer conflict check: the k nearest wholesale stockists to the
    given Ship To point, with drive times when Google is configured.
    conflict = any neighbor closer than maxMinutes (default from settings)."""
    return conflict.find_nearby(lat, lng, k, maxMinutes or settings.conflict_max_minutes)


@router.get("/accounts")
def lookup_accounts(
    email: str | None = Query(None, min_length=3, max_length=254),
    accountId: str | None = Query(None, min_length=15, max_length=18, pattern=r"^[a-zA-Z0-9]+$"),
    name: str | None = Query(None, min_length=2, max_length=255),
) -> dict:
    """Buyer lookup by email, account name (= store name) or Salesforce account
    id. Returns all candidates so the frontend can show a matching-account
    dropdown."""
    if not email and not accountId and not name:
        raise HTTPException(status_code=400, detail="Provide email, name or accountId")
    records = client.find_accounts(email=email, account_id=accountId, name=name)
    return {"matches": [mapping.map_account(r) for r in records]}
