from fastapi import APIRouter, HTTPException, Query, Response

from app.config import settings
from app.geo import conflict
from app.salesforce import account_search, client, mapping

router = APIRouter()


@router.get("/accounts/nearby")
def nearby_accounts(
    response: Response,
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    k: int = Query(5, ge=1, le=25),
    maxMinutes: int | None = Query(None, ge=1, le=240),
) -> dict:
    """New-customer conflict check: the k nearest wholesale stockists to the
    given Ship To point, with drive times when Google is configured.
    conflict = any neighbor closer than maxMinutes (default from settings)."""
    # Never reuse a cached result — the drive-time vs straight-line mode flips
    # when the Google server key is (re)configured, and a stale response would
    # keep showing "no drive times" after the key is fixed.
    response.headers["Cache-Control"] = "no-store"
    return conflict.find_nearby(lat, lng, k, maxMinutes or settings.conflict_max_minutes)


def account_city_state(rec: dict) -> str:
    """'Nashville, TN' — the only way to tell franchise locations apart."""
    return ", ".join(p for p in (rec.get("ShippingCity"), rec.get("ShippingState")) if p)


@router.get("/accounts/suggest")
def suggest_accounts(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(10, ge=1, le=25),
) -> dict:
    """Closest store-name matches, for when the exact lookup finds nothing.

    Payload is deliberately minimal — id, name, city/state. No email, tax id,
    rank or account notes: those load only when the buyer actively selects an
    account (GET /accounts?accountId=), not while they are still searching.

    Inactive / no-booking / OOB / not-going-forward accounts are excluded, the
    same rule the exact lookup uses — a buyer must not be able to order for a
    store that is closed.
    """
    rows = [
        r
        for r in client.account_search_index()
        if (r.get(mapping.RANK) or "") not in mapping.EXCLUDED_RANKS_FIND_ACCOUNT
    ]
    hits = account_search.search(rows, q, limit)
    return {
        "suggestions": [
            {"accountId": r["Id"], "name": r.get("Name"), "cityState": account_city_state(r)}
            for r in hits
        ]
    }


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
