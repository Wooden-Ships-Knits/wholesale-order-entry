"""POST /api/conflict-email — draft the internal "potential conflict nearby"
email to the rep for a new store that tripped the conflict check.

Returns text only; nothing is sent. Admin-only, because it is driven from the
admin order table and the admin conflict-check tab, and because generating it
from an order id exposes that order's buyer details and the stockist list.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.security import AdminRequired
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import conflict_template
from app.geo import conflict

logger = logging.getLogger(__name__)

router = APIRouter()

# Pull the 2-letter state out of "City, ST" or "…, ST 33101, USA".
_STATE_RE = re.compile(r",\s*([A-Z]{2})(?=\s+\d{5}|\s*,|\s*$)")

# Ask for a wide pool, then keep only the neighbors that are actually a
# conflict — the email lists those, like the on-screen check.
_POOL = 10


def _state_from(*texts: str | None) -> str | None:
    for text in texts:
        if text and (matches := _STATE_RE.findall(text)):
            return matches[-1]
    return None


def _coord(*values) -> float | None:
    for v in values:
        if v is not None:
            return float(v)
    return None


class ConflictEmailRequest(BaseModel):
    """Either an orderId (details come from the order) or the fields directly
    (the conflict-check tab has no order behind it). Supplied fields win, so a
    caller can override anything the order got wrong."""

    orderId: str | None = Field(None, max_length=36)
    storeName: str | None = Field(None, max_length=255)
    accountName: str | None = Field(None, max_length=255)
    repName: str | None = Field(None, max_length=255)
    salesTerritory: str | None = Field(None, max_length=255)
    state: str | None = Field(None, max_length=2)
    address: str | None = Field(None, max_length=500)
    email: str | None = Field(None, max_length=254)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    maxMinutes: int | None = Field(None, ge=1, le=240)


def _from_order(order: Order) -> dict:
    return {
        "store_name": order.buyer_name,
        "account_name": order.account_name,
        "rep_name": order.rep,
        "sales_territory": order.sales_territory,
        "state": _state_from(order.ship_city_state, order.bill_city_state),
        "lat": _coord(order.ship_lat, order.bill_lat),
        "lng": _coord(order.ship_lng, order.bill_lng),
    }


def _conflicting_neighbors(lat: float, lng: float, max_minutes: int) -> list[dict]:
    result = conflict.find_nearby(lat, lng, _POOL, max_minutes)
    straight_line = result["mode"] == "straight-line"

    def is_conflict(n: dict) -> bool:
        if n["driveMinutes"] is not None:
            return n["driveMinutes"] < max_minutes
        # Straight-line fallback: 20 min ≈ 10 mi (mirrors conflict.py).
        return straight_line and n["distanceMiles"] < max_minutes * 0.5

    return [n for n in result["neighbors"] if is_conflict(n)]


@router.post("/conflict-email", dependencies=[AdminRequired])
def conflict_email(payload: ConflictEmailRequest, db: Session = Depends(get_db)) -> dict:
    fields: dict = {}
    if payload.orderId:
        order = db.get(Order, payload.orderId)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        fields = _from_order(order)

    # Explicit fields override whatever the order supplied.
    overrides = {
        "store_name": payload.storeName,
        "account_name": payload.accountName,
        "rep_name": payload.repName,
        "sales_territory": payload.salesTerritory,
        "state": payload.state,
        "to_email": payload.email,
        "lat": payload.lat,
        "lng": payload.lng,
    }
    fields.update({k: v for k, v in overrides.items() if v is not None})

    if not fields.get("state"):
        fields["state"] = _state_from(payload.address)

    max_minutes = payload.maxMinutes or settings.conflict_max_minutes

    neighbors: list[dict] = []
    lat, lng = fields.get("lat"), fields.get("lng")
    if lat is not None and lng is not None:
        neighbors = _conflicting_neighbors(lat, lng, max_minutes)

    return conflict_template.build(
        # Prefer the store's business name; fall back to the buyer/contact name.
        store_name=fields.get("account_name") or fields.get("store_name"),
        rep_name=fields.get("rep_name"),
        sales_territory=fields.get("sales_territory"),
        state=fields.get("state"),
        neighbors=neighbors,
        to_email=fields.get("to_email"),
        max_minutes=max_minutes,
    )
