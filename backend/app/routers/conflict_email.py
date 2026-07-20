"""POST /api/conflict-email — draft the "we already have a stockist nearby"
email for a conflicting store.

Returns text only; nothing is sent. Admin-only, because it is driven from the
admin order table and the admin conflict-check tab, and because generating it
from an order id exposes that order's buyer details.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.security import AdminRequired
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import conflict_template

logger = logging.getLogger(__name__)

router = APIRouter()


class ConflictEmailRequest(BaseModel):
    """Either an orderId (details come from the order) or the fields directly
    (the conflict-check tab has no order behind it). Supplied fields win, so a
    caller can override anything the order got wrong."""

    orderId: str | None = Field(None, max_length=36)
    storeName: str | None = Field(None, max_length=255)
    contactName: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=254)
    address: str | None = Field(None, max_length=500)
    repName: str | None = Field(None, max_length=255)
    maxMinutes: int | None = Field(None, ge=1, le=240)


def _from_order(order: Order) -> dict:
    street = (order.ship_street or order.bill_street or "").strip()
    city = (order.ship_city_state or order.bill_city_state or "").strip()
    zip_code = (order.ship_zip or order.bill_zip or "").strip()
    address = ", ".join(p for p in (street, city, zip_code) if p)
    return {
        "store_name": order.buyer_name,
        "contact_name": order.signature_name or order.buyer_name,
        "to_email": order.ship_email,
        "address": address,
        "rep_name": order.rep,
    }


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
        "contact_name": payload.contactName,
        "to_email": payload.email,
        "address": payload.address,
        "rep_name": payload.repName,
    }
    fields.update({k: v for k, v in overrides.items() if v})

    return conflict_template.build(
        **fields,
        max_minutes=payload.maxMinutes or settings.conflict_max_minutes,
    )
