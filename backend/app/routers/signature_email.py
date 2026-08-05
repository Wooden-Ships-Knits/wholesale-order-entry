"""POST /api/signature-email — draft the "review and sign your order" email.

Admin-only, and the mint point for the signing token: generating the draft
creates (or reuses) the token embedded in the link, because the body cannot be
written without it. Nothing is sent here — the admin edits the draft and sends
it through POST /api/send-email with kind="signature", which stamps
signature_requested_at and records where it went.

Regenerating a draft REUSES an unexpired token rather than minting a second
one. Minting per draft would leave the earlier link live and unaccounted for:
two working credentials for the same order, only one of which the admin knows
they sent.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.security import AdminRequired
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import signature_template
from app.routers.sign import mint_token, sign_url
from app.salesforce import mapping
from app.sheets import client as sheets_client

logger = logging.getLogger(__name__)

router = APIRouter()


class SignatureEmailRequest(BaseModel):
    orderId: str = Field(max_length=36)
    # Override the recipient; defaults to the order's Ship To email.
    email: str | None = Field(None, max_length=254)


@router.post("/signature-email", dependencies=[AdminRequired])
def signature_email(payload: SignatureEmailRequest, db: Session = Depends(get_db)) -> dict:
    order = db.get(Order, payload.orderId)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.signature_signed_at is not None:
        raise HTTPException(
            status_code=409, detail="This order has already been signed by the buyer."
        )

    now = datetime.now(timezone.utc)
    expired = (
        order.signature_token_expires_at is not None
        and order.signature_token_expires_at < now
    )
    if not order.signature_token or expired:
        order.signature_token, order.signature_token_expires_at = mint_token()
        db.commit()
        logger.info("Minted a signing token for order %s", str(order.id)[:8])

    draft = signature_template.build(
        to_email=payload.email or order.signature_email or order.ship_email,
        sign_url=sign_url(order.signature_token),
        # Lead rep for the order's territory; blank when unknown, and the
        # admin can edit it in the modal before sending.
        cc_email=sheets_client.rep_email_for_territory(order.sales_territory),
        account_name=order.account_name,
        buyer_name=order.buyer_name,
        season_label=mapping.season_label(order.season_code),
        total_qty=order.total_qty,
        total_amount=order.total_amount,
        expires_days=settings.signature_link_days,
        short_id=str(order.id)[:8],
    )
    # The link is in the body by necessity; keep it out of the logs.
    logger.info("Drafted a signature request for order %s", str(order.id)[:8])
    return draft
