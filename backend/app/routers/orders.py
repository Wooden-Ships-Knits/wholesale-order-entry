"""POST /api/orders — validate, render PDF, persist (NO card number), respond.

Prices and Salesforce product ids are re-resolved server-side from the
season's wholesale price book; client-sent prices are ignored. Card number
and CVV are never persisted, logged, or rendered: only card_name + last4
are stored, and the PDF shows just those. The PDF is rendered BEFORE the DB
commit — a render failure aborts the whole submission so the buyer can
retry — and written to PDF_OUTPUT_DIR after the commit succeeds.

For new accounts with Ship To coordinates, the nearby-stockist conflict check
runs as a background task once the response is out; its boolean verdict lands
on orders.has_conflict for the admin page.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crypto
from app.config import settings
from app.db.models import Order
from app.db.session import SessionLocal, get_db
from app.email import mailer, order_email, signature_template
from app.geo import conflict
from app.pdf import context as pdf_context_builder
from app.pdf import render as pdf_render
from app.routers import sign
from app.salesforce import mapping
from app.schemas.order import OrderSubmission
from app.services import order_lines
from app.sheets import client as sheets_client

logger = logging.getLogger(__name__)

router = APIRouter()

SHIP_WINDOW_NOTE = "Please allow 7–12 days for transit."

# How many neighbours the conflict check looks at (matches the endpoint default).
CONFLICT_NEIGHBOURS = 5


def _fail(errors: list[dict]) -> None:
    raise HTTPException(status_code=422, detail={"errors": errors})


def _is_new_account(payload: OrderSubmission) -> bool | None:
    """Is this a new account? Depends on who filled the form.

    A rep answers the Internal Use "New account / Existing" radio; a customer
    answers "is this your first order?" (the Internal Use section isn't shown
    to them). None when unanswered, so the admin page shows "—" rather than a
    misleading "No".
    """
    if payload.filled_by == "customer":
        return payload.first_order
    if payload.internal.account_status == "new":
        return True
    if payload.internal.account_status == "existing":
        return False
    return None


def _conflict_point(order: Order) -> tuple[float, float] | None:
    """Coordinates to run the conflict check from.

    Ship To is the store location and what the spec calls for; fall back to
    Bill To so a buyer who only searched the billing map still gets checked.
    """
    if order.ship_lat is not None and order.ship_lng is not None:
        return float(order.ship_lat), float(order.ship_lng)
    if order.bill_lat is not None and order.bill_lng is not None:
        return float(order.bill_lat), float(order.bill_lng)
    return None


def _send_signature_request(order_id: uuid.UUID) -> None:
    """Background: email the buyer their signing link, then record the send.

    signature_requested_at is stamped only AFTER the SMTP call succeeds, so the
    admin column's "Email Sent ✓" means the mail really left. A failure leaves
    it null — the order shows as still needing a signature and the team can
    resend from /admin, which is the honest outcome. The token is already
    committed either way, so the resend reuses the same link.
    """
    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        if order is None or not order.signature_token:
            return
        draft = signature_template.build(
            to_email=order.signature_email,
            sign_url=sign.sign_url(order.signature_token),
            account_name=order.account_name,
            buyer_name=order.buyer_name,
            season_label=mapping.season_label(order.season_code),
            total_qty=order.total_qty,
            total_amount=order.total_amount,
            expires_days=settings.signature_link_days,
        )
        # CC the territory's lead rep, same lookup as the tax-cert request.
        # None when the territory is empty or has no rep row — send anyway
        # rather than hold the buyer's link hostage to a sheet lookup.
        cc = sheets_client.rep_email_for_territory(order.sales_territory)
        if not cc:
            logger.info(
                "No rep email for territory %r — signature request for order %s sent without CC",
                order.sales_territory, str(order_id)[:8],
            )
        if not mailer.send_email(draft["to"], draft["subject"], draft["body"], cc=cc):
            logger.error(
                "Signature request for order %s could not be sent — resend from /admin",
                str(order_id)[:8],
            )
            return
        order.signature_requested_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("Signature request sent for order %s", str(order_id)[:8])
    except Exception:
        logger.exception("Signature request failed for order %s", str(order_id)[:8])
        db.rollback()
    finally:
        db.close()


def _run_conflict_check(order_id: uuid.UUID, lat: float, lng: float) -> None:
    """Background: store the nearby-stockist verdict on the order.

    Runs after the response is sent, with its own session — the request's is
    already closed. Failures leave has_conflict null ("not checked"), never
    False: a wrong "no conflict" would silently approve a competing stockist.
    """
    try:
        result = conflict.find_nearby(lat, lng, CONFLICT_NEIGHBOURS, settings.conflict_max_minutes)
    except Exception:
        logger.exception("Conflict check failed for order %s", str(order_id)[:8])
        return

    db = SessionLocal()
    try:
        order = db.get(Order, order_id)
        if order is None:
            return
        order.has_conflict = result["conflict"]
        db.commit()
        logger.info(
            "Conflict check for order %s: %s (%s)",
            str(order_id)[:8],
            result["conflict"],
            result["mode"],
        )
    except Exception:
        logger.exception("Could not store conflict verdict for order %s", str(order_id)[:8])
        db.rollback()
    finally:
        db.close()


@router.post("/orders", status_code=201)
def submit_order(
    payload: OrderSubmission,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    errors: list[dict] = []

    # The policies are the BUYER's to accept. A rep-filled order is on its way
    # to them, so the acknowledgement comes later: the signing page shows the
    # same policies and POST /api/sign/{token} sets terms_accepted. Requiring
    # it here would make a rep tick a box on the buyer's behalf — and, since
    # the form no longer shows it to reps, would block every rep order.
    if not payload.terms.draft_signature and not payload.terms.accepted:
        errors.append({"code": "terms", "message": "Terms & conditions must be accepted."})
    # Either the buyer signs here, or the order is emailed to them to sign.
    # No separate recipient to validate: it's the Ship To email, which
    # OrderSubmission already requires.
    if not payload.terms.draft_signature and not payload.terms.signature_name.strip():
        errors.append({"code": "signature", "message": "Signature is required."})

    # Quantities → priced lines. Shared with the signature-link path, so both
    # re-resolve prices from the price book and enforce the same minimums.
    # Errors accumulate with the terms ones above: the buyer sees everything
    # wrong in one response rather than fixing them one round-trip at a time.
    items = [i for i in payload.items if i.pieces > 0]
    order_items, total_qty, total_amount, line_errors = order_lines.build(
        payload.season, items
    )
    errors.extend(line_errors)
    if errors:
        _fail(errors)

    # Card handling: derive last4, then never touch the number again here.
    card_digits = payload.payment.card_number.get_secret_value().replace(" ", "")
    card_last4 = card_digits[-4:] if len(card_digits) >= 4 else None

    campaign = payload.internal.campaign
    if campaign == "other" and payload.internal.campaign_other:
        campaign = f"Other: {payload.internal.campaign_other}"
    split_with = (
        f"Y — {payload.internal.split_with}".strip(" —")
        if payload.internal.split is True
        else ("N" if payload.internal.split is False else "")
    )

    # Uploaded tax-exemption certificate: decode now (schema already validated
    # extension, base64 and size) so a bad file fails before anything persists.
    order_id = uuid.uuid4()
    created_at = datetime.now(timezone.utc)
    cert_bytes: bytes | None = None
    cert_name: str | None = None
    if payload.tax_exemption.cert_file is not None:
        cert_bytes = payload.tax_exemption.cert_file.decoded()
        cert_name = pdf_render.cert_filename(
            payload.season,
            payload.bill_to.buyer_name,
            created_at,
            order_id,
            payload.tax_exemption.cert_file.name,
        )

    order = Order(
        id=order_id,
        season_code=payload.season,
        order_date=payload.order_date,
        part_ship_ok=payload.part_ship_ok,
        ship_window_note=SHIP_WINDOW_NOTE,
        ship_window=payload.ship_window,
        filled_by=payload.filled_by,
        notes=payload.notes,
        buyer_name=payload.bill_to.buyer_name,
        bill_street=payload.bill_to.street,
        bill_city_state=payload.bill_to.city_state,
        bill_zip=payload.bill_to.zip,
        tel=payload.bill_to.tel,
        fax=payload.bill_to.fax,
        bill_lat=payload.bill_to.lat,
        bill_lng=payload.bill_to.lng,
        ship_email=str(payload.ship_to.email),
        ship_street=payload.ship_to.street,
        ship_city_state=payload.ship_to.city_state,
        ship_zip=payload.ship_to.zip,
        resale_tax_id=payload.ship_to.resale_tax_id,
        ship_lat=payload.ship_to.lat,
        ship_lng=payload.ship_to.lng,
        payment_method=payload.payment.method,
        approval_before_charge=payload.payment.approval_before_charge,
        card_name=payload.payment.card_name,
        card_last4=card_last4,
        card_exp=payload.payment.exp_date or None,
        cert_required_ack=payload.tax_exemption.rep_notified,
        cert_sending_ack=payload.tax_exemption.sending_cert,
        cert_on_file=payload.tax_exemption.cert_on_file,
        cert_filename=cert_name,
        signature_name=payload.terms.signature_name,
        signature_date=payload.terms.signature_date,
        terms_accepted=payload.terms.accepted,
        order_copy_email=str(payload.terms.order_copy_email) if payload.terms.order_copy_email else None,
        new_or_reorder=payload.internal.new_or_reorder,
        account_status=payload.internal.account_status,
        is_new_account=_is_new_account(payload),
        campaign=campaign,
        po_number=payload.internal.po_number,
        rep=payload.internal.rep,
        order_written_by=payload.internal.order_written_by,
        split_with=split_with,
        sf_account_id=payload.sf_account_id,
        sales_territory=payload.sales_territory,
        rank=payload.rank,
        account_name=payload.account_name,
        special_instructions=payload.special_instructions,
        total_qty=total_qty,
        total_amount=total_amount,
        status="submitted",
        items=order_items,
    )
    # "Send the draft to the buyer to sign": mint the link now, so the token is
    # committed with the order and the email task below has something to point
    # at. signature_requested_at is NOT set here — it means "the email actually
    # went out", and that is only known once the send succeeds.
    if payload.terms.draft_signature:
        # Ship To is the buyer's own address and is already required, so it is
        # the recipient. draft_signature_email is still honoured if a caller
        # sends one, but the form no longer asks for it.
        order.signature_email = str(payload.terms.draft_signature_email or payload.ship_to.email)
        order.signature_token, order.signature_token_expires_at = sign.mint_token()
    # Render the PDF BEFORE committing: card details exist only in this
    # request, so a failed render must fail the submission (nothing persisted,
    # buyer retries). The context dict below is the only place the full card
    # number/CVV are read, and it goes out of scope at the end of this call.
    # created_at / items are passed explicitly: the row isn't committed yet, so
    # the server-default timestamp and the items relationship aren't readable.
    pdf_context = pdf_context_builder.build(order, created_at=created_at, items=order_items)

    # Two renders from one template:
    #   masked — number shown as "•••• 1234". Saved to disk and emailed.
    #   admin  — full number, for the monitoring team to key into Salesforce.
    #            Encrypted immediately, held in the DB, never written to disk
    #            and never emailed. See CLAUDE.md rule 1.
    masked_card = {
        "name": order.card_name or None,
        "number": f"•••• {card_last4}" if card_last4 else None,
        "exp": order.card_exp or None,
        "full": False,
    }
    try:
        pdf_context["card"] = masked_card
        pdf_bytes = pdf_render.render_order_pdf(pdf_context)

        # Only worth keeping an admin copy if there is a card AND a key to
        # protect it with; without a key the number is simply discarded.
        if card_digits and crypto.configured():
            pdf_context["card"] = {**masked_card, "number": card_digits, "full": True}
            order.card_pdf_enc = crypto.encrypt(pdf_render.render_order_pdf(pdf_context))
        elif card_digits:
            logger.warning(
                "CARD_ENCRYPTION_KEY not set — no admin card copy kept for this order"
            )
    except Exception:
        logger.exception("PDF rendering failed for order attempt (season=%s)", payload.season)
        raise HTTPException(
            status_code=500,
            detail="The order could not be processed (PDF generation failed). Please try again.",
        )
    finally:
        # Drop every in-memory reference to the number before the request ends.
        pdf_context["card"] = None
        pdf_context["payment"] = None
        card_digits = ""

    db.add(order)
    db.commit()

    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name, created_at, order.id
    )
    try:
        pdf_render.save_order_pdf(pdf_bytes, filename)
        pdf_saved = True
    except OSError:
        # Order is committed; card data is gone with this request. Surface
        # loudly in logs so admin can follow up with the buyer.
        logger.exception("CRITICAL: order %s committed but PDF could not be written", order.id)
        pdf_saved = False

    if cert_bytes is not None and cert_name is not None:
        try:
            pdf_render.save_output_file(cert_bytes, cert_name)
        except OSError:
            logger.exception(
                "CRITICAL: order %s committed but tax cert %s could not be written",
                order.id, cert_name,
            )

    # Email the admin (wholesale@wooden-ships.com) a copy of every order
    # (re-enabled 2026-07-24, reversing the 2026-07-23 pause). Admin copy ONLY —
    # and the buyer's own copy when they asked for one. Both are background
    # tasks (like the conflict check below) so a slow or failed Gmail never
    # blocks the buyer's confirmation screen. The attachment is the in-memory,
    # card-masked PDF — so it sends even if the disk save above failed.
    # Accept/Decline still emails the buyer nothing; the team words that itself
    # through the draft modal (POST /api/send-email).
    email_ctx = {
        "short_id": str(order.id)[:8],
        "season_code": order.season_code,
        "season_label": mapping.season_label(order.season_code),
        # The store is what identifies an order in the admin inbox — buyer
        # first names repeat across stores and Gmail truncates the subject.
        "account_name": order.account_name,
        "buyer_name": order.buyer_name,
        "total_qty": total_qty,
        "total_amount": total_amount,
    }
    background.add_task(order_email.send_admin_copy, email_ctx, pdf_bytes, filename)

    # Buyer's own copy, only when they ticked the box on the form. The
    # attachment is the same in-memory, card-masked PDF, so it sends even if
    # the disk write above failed. Explicitly a records copy, not a
    # confirmation — the order is still reviewed in /admin and may be declined.
    if order.order_copy_email:
        background.add_task(
            order_email.send_buyer_copy, order.order_copy_email, email_ctx, pdf_bytes, filename
        )

    # The buyer asked us to send the order out for signature. Background, like
    # the copies above: a slow Gmail must not hold up the confirmation screen.
    if order.signature_token:
        background.add_task(_send_signature_request, order.id)

    # New accounts only: check whether an existing stockist is too close, so
    # /admin can flag it. Runs in the background — a slow Google/Salesforce
    # round-trip must not hold up the buyer's confirmation. Needs the Ship To
    # coordinates from the form's Places search; without them the verdict
    # stays null ("not checked") rather than a misleading "no conflict".
    if order.is_new_account:
        point = _conflict_point(order)
        if point is None:
            logger.info(
                "Order %s is a new account but has no coordinates — conflict unchecked",
                str(order.id)[:8],
            )
        else:
            background.add_task(_run_conflict_check, order.id, *point)

    logger.info(
        "Order %s persisted: season=%s items=%d qty=%d total=%s pdf=%s",
        order.id, payload.season, len(order_items), total_qty, total_amount, filename,
    )
    return {
        "orderId": str(order.id),
        "status": order.status,
        "totalQty": total_qty,
        "totalAmount": float(total_amount),
        "pdfGenerated": pdf_saved,
    }
