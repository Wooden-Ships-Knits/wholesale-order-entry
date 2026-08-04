"""/api/sign/{token} — the buyer reviews, optionally adjusts, and signs.

The ONLY unauthenticated write endpoints in the app. The token is a bearer
credential minted by /api/signature-email and mailed to the buyer: whoever
holds the URL can edit and sign that one order. Consequences of that, all
deliberate:

* The token is random (`secrets.token_urlsafe`), never the order id — order
  ids appear in admin URLs, log lines and PDF filenames, so using one as the
  credential would make orders signable by anyone who has ever seen an id.
* It is single-use (nulled on signing) and expires.
* Tokens are never logged. Errors quote the order's short id instead.
* The GET response is hand-built below, NOT the admin serializer. Rank,
  special instructions, sales territory, internal-use fields and card data
  beyond the last 4 must never cross this boundary.

Editing re-prices every line from the season price book (app/services/
order_lines.py) and re-checks the minimums, so a buyer can change quantities
but cannot influence what they cost.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import order_email
from app.pdf import context as pdf_context_builder
from app.pdf import render as pdf_render
from app.salesforce import mapping
from app.schemas.order import CamelModel, OrderItemIn
from app.services import order_lines

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sign")

# Tokens are compared by an indexed equality lookup, so length is the defence.
# 32 bytes -> 43 url-safe characters.
TOKEN_BYTES = 32


def mint_token() -> tuple[str, datetime]:
    """A fresh signature token and its expiry. Used by the admin email route."""
    return (
        secrets.token_urlsafe(TOKEN_BYTES),
        datetime.now(timezone.utc) + timedelta(days=settings.signature_link_days),
    )


def sign_url(token: str) -> str:
    base = (settings.public_base_url or settings.cors_origin).rstrip("/")
    return f"{base}/sign/{token}"


class SignRequest(CamelModel):
    signature_name: str = Field(min_length=1, max_length=200)
    # The order as the buyer wants it. Sent in full (not as a diff) so the
    # server never has to reconcile partial state against what it holds.
    items: list[OrderItemIn] = Field(default_factory=list, max_length=200)


def _order_for_token(db: Session, token: str) -> Order:
    """Resolve a token to its order, or raise. Never logs the token itself."""
    order = db.scalar(select(Order).where(Order.signature_token == token))
    if order is None:
        # Covers "never existed", "already signed" and "revoked" alike — an
        # unauthenticated caller learns nothing about which.
        raise HTTPException(status_code=404, detail="This signing link is no longer valid.")
    expires = order.signature_token_expires_at
    if expires is not None and expires < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=410,
            detail="This signing link has expired. Please ask us to send a new one.",
        )
    return order


def _public_view(order: Order) -> dict:
    """What the buyer is allowed to see. Add fields here only after asking
    whether a stranger holding the link should read them."""
    return {
        "orderId": str(order.id)[:8],
        "season": order.season_code,
        "seasonLabel": mapping.season_label(order.season_code),
        "orderDate": order.order_date,
        "shipWindow": order.ship_window,
        "shipWindowNote": order.ship_window_note,
        "accountName": order.account_name,
        "buyerName": order.buyer_name,
        "billTo": {
            "street": order.bill_street,
            "cityState": order.bill_city_state,
            "zip": order.bill_zip,
            "tel": order.tel,
        },
        "shipTo": {
            "email": order.ship_email,
            "street": order.ship_street,
            "cityState": order.ship_city_state,
            "zip": order.ship_zip,
        },
        # Enough for the buyer to recognise their own card. The number itself
        # is not stored as a column and is not available here at all.
        "payment": {"method": order.payment_method, "cardLast4": order.card_last4},
        "poNumber": order.po_number,
        "notes": order.notes,
        "items": [
            {
                "styleName": i.style_name,
                "color": i.color,
                "qtyXs": i.qty_xs,
                "qtySm": i.qty_sm,
                "qtyMl": i.qty_ml,
                "unitPrice": float(i.unit_price),
                "lineTotal": float(i.line_total),
            }
            for i in order.items
        ],
        "totalQty": order.total_qty,
        "totalAmount": float(order.total_amount),
        "signed": order.signature_signed_at is not None,
    }


@router.get("/{token}")
def get_order_for_signing(token: str, db: Session = Depends(get_db)) -> dict:
    return _public_view(_order_for_token(db, token))


@router.post("/{token}")
def sign_order(
    token: str,
    payload: SignRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    order = _order_for_token(db, token)
    short_id = str(order.id)[:8]

    # The other half of the admin freeze (see admin._reject_if_awaiting_signature).
    # An accepted order is already in Salesforce as a Kugamon Draft; letting a
    # link signed afterwards rewrite the lines here would leave the two systems
    # permanently disagreeing. Declined is simpler — there is nothing to sign.
    if order.status != "submitted":
        raise HTTPException(
            status_code=409,
            detail=(
                "This order has already been reviewed by our team, so it can no longer "
                "be signed here. Please reply to our email and we'll help."
            ),
        )

    items = [i for i in payload.items if i.pieces > 0]
    order_items, total_qty, total_amount, errors = order_lines.build(
        order.season_code, items
    )
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    # Snapshot the order as the rep wrote it, once, before the first edit — so
    # /admin can show that the buyer changed it. Guarded because a resend must
    # not overwrite the original with an already-edited version.
    if order.orig_total_qty is None:
        order.orig_total_qty = order.total_qty
        order.orig_total_amount = order.total_amount

    # Replace the lines wholesale. delete-orphan on the relationship issues the
    # DELETEs; the whole swap rides the request's transaction, so a failure
    # below leaves the original lines intact.
    order.items = order_items
    order.total_qty = total_qty
    order.total_amount = total_amount

    signed_at = datetime.now(timezone.utc)
    order.signature_name = payload.signature_name.strip()
    order.signature_date = signed_at.date()
    order.signature_signed_at = signed_at
    order.terms_accepted = True
    # Spend the token: the link works exactly once.
    order.signature_token = None
    order.signature_token_expires_at = None

    # Re-render the masked PDF so the stored copy shows the signature and the
    # final quantities. Only the masked copy can be rebuilt here — the card
    # number lives solely in the submit request, so card_pdf_enc is untouched.
    try:
        pdf_context = pdf_context_builder.build(order, items=order_items)
        pdf_context["card"] = {
            "name": order.card_name or None,
            "number": f"•••• {order.card_last4}" if order.card_last4 else None,
            "exp": order.card_exp or None,
            "full": False,
        }
        pdf_bytes = pdf_render.render_order_pdf(pdf_context)
    except Exception:
        logger.exception("Signature PDF render failed for order %s", short_id)
        raise HTTPException(
            status_code=500,
            detail="Your signature could not be saved (PDF generation failed). Please try again.",
        )

    db.commit()

    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )
    try:
        pdf_render.save_order_pdf(pdf_bytes, filename)
    except OSError:
        # Signature is committed; the PDF on disk is now the pre-signature one.
        # Loud, because the admin copy below still carries the correct version.
        logger.exception(
            "CRITICAL: order %s signed but the signed PDF could not be written", short_id
        )

    email_ctx = {
        "short_id": short_id,
        "season_code": order.season_code,
        "season_label": mapping.season_label(order.season_code),
        "account_name": order.account_name,
        "buyer_name": order.buyer_name,
        "total_qty": total_qty,
        "total_amount": total_amount,
    }
    background.add_task(order_email.send_admin_copy, email_ctx, pdf_bytes, filename)
    if order.order_copy_email:
        background.add_task(
            order_email.send_buyer_copy, order.order_copy_email, email_ctx, pdf_bytes, filename
        )

    logger.info(
        "Order %s signed by the buyer: qty %s -> %s, total %s -> %s",
        short_id, order.orig_total_qty, total_qty, order.orig_total_amount, total_amount,
    )
    return {"signed": True, "orderId": short_id, "totalQty": total_qty,
            "totalAmount": float(total_amount)}
