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
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import order_email
from app.pdf import context as pdf_context_builder
from app.pdf import render as pdf_render
from app.salesforce import mapping
from app.schemas.order import BillTo, CamelModel, OrderItemIn, Payment, ShipTo
from app.services import order_lines
from app.sheets import client as sheets_client

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

    # Everything the buyer may correct while reviewing. Reuses the order form's
    # own models so the two paths validate identically — a rule that changes on
    # /api/orders can't quietly not apply here. All optional: an unchanged
    # section is simply absent and the stored value stands.
    #
    # NOT accepted, deliberately: season (fixes the price book every line was
    # costed against), account name / sf_account_id (reassigning a store is an
    # admin action) and the Internal Use block (rep-only, never shown here).
    bill_to: BillTo | None = None
    ship_to: ShipTo | None = None
    order_date: date | None = None
    ship_window: str = Field("", max_length=120)
    po_number: str = Field("", max_length=100)
    notes: str = Field("", max_length=5000)
    payment: Payment | None = None


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
        # Read-only on the page: reassigning the store is an admin action, and
        # the season fixes which price book every line was costed against.
        "buyerName": order.buyer_name,
        "billTo": {
            "buyerName": order.buyer_name,
            "street": order.bill_street,
            "cityState": order.bill_city_state,
            "zip": order.bill_zip,
            "tel": order.tel,
            "fax": order.fax,
            "lat": float(order.bill_lat) if order.bill_lat is not None else None,
            "lng": float(order.bill_lng) if order.bill_lng is not None else None,
        },
        "shipTo": {
            "email": order.ship_email,
            "street": order.ship_street,
            "cityState": order.ship_city_state,
            "zip": order.ship_zip,
            "resaleTaxId": order.resale_tax_id,
            "lat": float(order.ship_lat) if order.ship_lat is not None else None,
            "lng": float(order.ship_lng) if order.ship_lng is not None else None,
        },
        # Enough for the buyer to recognise their own card, and to re-enter one
        # if it changed. The NUMBER is not a column and is not available here —
        # it exists only inside the encrypted admin PDF (CLAUDE.md rule 1), so
        # the page offers "use a different card" rather than a prefilled field.
        "payment": {
            "method": order.payment_method,
            "approvalBeforeCharge": order.approval_before_charge,
            "cardName": order.card_name,
            "cardExp": order.card_exp,
            "cardLast4": order.card_last4,
        },
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

    # The saved PDF's filename embeds the buyer name, which the buyer may be
    # about to correct — capture the current one so the superseded file can be
    # removed after the new one is written.
    prev_filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )

    # ---- corrections the buyer made while reviewing ----
    if payload.bill_to is not None:
        b = payload.bill_to
        order.buyer_name = b.buyer_name
        order.bill_street, order.bill_city_state, order.bill_zip = b.street, b.city_state, b.zip
        order.tel, order.fax = b.tel, b.fax
        # Only overwrite coordinates when the page actually resolved an address;
        # a null would silently un-check the stockist-conflict verdict.
        if b.lat is not None and b.lng is not None:
            order.bill_lat, order.bill_lng = b.lat, b.lng
    if payload.ship_to is not None:
        s = payload.ship_to
        order.ship_email = str(s.email)
        order.ship_street, order.ship_city_state, order.ship_zip = s.street, s.city_state, s.zip
        order.resale_tax_id = s.resale_tax_id
        if s.lat is not None and s.lng is not None:
            order.ship_lat, order.ship_lng = s.lat, s.lng
    if payload.order_date is not None:
        order.order_date = payload.order_date
    if payload.ship_window.strip():
        order.ship_window = payload.ship_window.strip()
    order.po_number = payload.po_number.strip() or None
    order.notes = payload.notes.strip() or None

    # The copy follows the Ship To address, which the buyer may have just
    # corrected above — send it where they can actually read it.
    order.order_copy_email = order.ship_email

    signed_at = datetime.now(timezone.utc)
    order.signature_name = payload.signature_name.strip()
    order.signature_date = signed_at.date()
    order.signature_signed_at = signed_at
    order.terms_accepted = True
    # Spend the token: the link works exactly once.
    order.signature_token = None
    order.signature_token_expires_at = None

    # ---- payment ----
    # CLAUDE.md rule 1 holds exactly as on submit: the number is read once,
    # here, to derive last4 and to draw the encrypted admin copy. It is never a
    # column, never logged, never emailed. CVV is read by nothing.
    card_digits = ""
    if payload.payment is not None:
        p = payload.payment
        if p.method:
            order.payment_method = p.method
        if p.approval_before_charge is not None:
            order.approval_before_charge = p.approval_before_charge
        card_digits = p.card_number.get_secret_value().replace(" ", "")
        if card_digits:
            # A replacement card: everything derived from it is refreshed
            # together, so last4/name/exp can't describe a different card.
            order.card_last4 = card_digits[-4:] if len(card_digits) >= 4 else None
            order.card_name = p.card_name or None
            order.card_exp = p.exp_date or None
        elif p.card_name or p.exp_date:
            # Name/expiry corrected without re-entering the number.
            order.card_name = p.card_name or order.card_name
            order.card_exp = p.exp_date or order.card_exp

    # Re-render the masked PDF so the stored copy shows the signature and the
    # final quantities, and the admin copy too when a new card was supplied.
    try:
        pdf_context = pdf_context_builder.build(order, items=order_items)
        masked_card = pdf_context_builder.masked_card(order)
        pdf_context["card"] = masked_card
        pdf_bytes = pdf_render.render_order_pdf(pdf_context)

        # Only when the buyer entered a NEW number — otherwise the copy made at
        # submit still holds the card the team has to key in, and this request
        # has no number to rebuild it from.
        if card_digits and crypto.configured():
            pdf_context["card"] = {**masked_card, "number": card_digits, "full": True}
            order.card_pdf_enc = crypto.encrypt(pdf_render.render_order_pdf(pdf_context))
            logger.info("Order %s: card replaced at signing, admin copy re-encrypted", short_id)
        elif card_digits:
            logger.warning(
                "CARD_ENCRYPTION_KEY not set — no admin card copy kept for order %s", short_id
            )
    except Exception:
        logger.exception("Signature PDF render failed for order %s", short_id)
        raise HTTPException(
            status_code=500,
            detail="Your signature could not be saved (PDF generation failed). Please try again.",
        )
    finally:
        # Drop every in-memory reference to the number before the request ends.
        pdf_context["card"] = None
        card_digits = ""

    db.commit()

    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )
    try:
        pdf_render.save_order_pdf(pdf_bytes, filename)
        # Only once the signed copy is safely written: if the buyer corrected
        # their name, the old filename now points at a stale, unsigned PDF that
        # nothing reads. Deleting before the write would risk losing both.
        if filename != prev_filename:
            pdf_render.delete_output_file(prev_filename)
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
    background.add_task(order_email.send_signed_copy, email_ctx, pdf_bytes, filename)

    # The order copy, addressed to the buyer and the territory's rep, so the
    # rep always receives the PDF the buyer actually signed — which may differ
    # from the one they sent out, since quantities are editable on this page.
    # This is the rep's copy of a rep-filled order; they are not on the notice
    # above.
    rep_to = sheets_client.rep_email_for_territory(order.sales_territory)
    if not rep_to:
        logger.info(
            "No rep email for territory %r — order %s copy sent to the buyer only",
            order.sales_territory, short_id,
        )
    background.add_task(
        order_email.send_order_copy,
        order.order_copy_email, email_ctx, pdf_bytes, filename, rep=rep_to,
    )

    logger.info(
        "Order %s signed by the buyer: qty %s -> %s, total %s -> %s",
        short_id, order.orig_total_qty, total_qty, order.orig_total_amount, total_amount,
    )
    return {"signed": True, "orderId": short_id, "totalQty": total_qty,
            "totalAmount": float(total_amount)}
