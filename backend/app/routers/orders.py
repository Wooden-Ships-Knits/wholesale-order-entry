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
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Order, OrderItem
from app.db.session import SessionLocal, get_db
from app.email import order_email
from app.geo import conflict
from app.pdf import render as pdf_render
from app.salesforce import client, mapping
from app.schemas.order import OrderSubmission
from app.validation.order_minimum import validate_minimums

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

    if not payload.terms.accepted:
        errors.append({"code": "terms", "message": "Terms & conditions must be accepted."})
    if not payload.terms.signature_name.strip():
        errors.append({"code": "signature", "message": "Signature is required."})

    items = [i for i in payload.items if i.pieces > 0]
    if not items:
        errors.append({"code": "no_items", "message": "The order has no quantities."})

    errors.extend(validate_minimums(items))
    if errors:
        _fail(errors)

    # Resolve the season's wholesale price book — authoritative prices + ids.
    books = {
        mapping.season_from_pricebook_name(b["Name"]): b
        for b in client.list_wholesale_pricebooks()
    }
    book = books.get(payload.season)
    if book is None:
        _fail([{"code": "season", "message": f"Unknown season {payload.season}."}])
    rows, _stats = mapping.group_products(client.get_pricebook_entries(book["Id"]))
    catalog = {(r["styleName"], r["color"]): r for r in rows}

    order_items: list[OrderItem] = []
    total_qty = 0
    total_amount = Decimal("0")
    for item in items:
        row = catalog.get((item.style_name, item.color))
        if row is None:
            errors.append(
                {
                    "code": "unknown_product",
                    "style": item.style_name,
                    "color": item.color,
                    "message": f'"{item.style_name} — {item.color}" is not in the {payload.season} wholesale catalog.',
                }
            )
            continue
        unit_price = Decimal(str(row["unitPrice"] or 0)).quantize(Decimal("0.01"))
        line_qty = item.pieces
        line_total = (unit_price * line_qty).quantize(Decimal("0.01"))
        total_qty += line_qty
        total_amount += line_total
        order_items.append(
            OrderItem(
                sf_product_id_xs=row["sizes"]["xs"] if item.qty_xs else None,
                sf_product_id_sm=row["sizes"]["sm"] if item.qty_sm else None,
                sf_product_id_ml=row["sizes"]["ml"] if item.qty_ml else None,
                code=row["code"],
                style_name=item.style_name,
                color=item.color,
                qty_xs=item.qty_xs,
                qty_sm=item.qty_sm,
                qty_ml=item.qty_ml,
                line_qty=line_qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )
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
        account_name=payload.account_name,
        special_instructions=payload.special_instructions,
        total_qty=total_qty,
        total_amount=total_amount,
        status="submitted",
        items=order_items,
    )
    # Render the PDF BEFORE committing: card details exist only in this
    # request, so a failed render must fail the submission (nothing persisted,
    # buyer retries). The context dict below is the only place the full card
    # number/CVV are read, and it goes out of scope at the end of this call.
    pdf_context = {
        "order": {
            "short_id": str(order.id)[:8],
            "season_code": order.season_code,
            "season_label": mapping.season_label(order.season_code),
            "order_date": order.order_date,
            "part_ship_ok": order.part_ship_ok,
            "ship_window_note": order.ship_window_note,
            "ship_window": order.ship_window,
            "filled_by": order.filled_by,
            "notes": order.notes,
            "payment_method": order.payment_method,
            "approval_before_charge": order.approval_before_charge,
            "cert_filename": order.cert_filename,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M UTC"),
            "buyer_name": order.buyer_name,
            "bill_street": order.bill_street,
            "bill_city_state": order.bill_city_state,
            "bill_zip": order.bill_zip,
            "tel": order.tel,
            "fax": order.fax,
            "ship_email": order.ship_email,
            "ship_street": order.ship_street,
            "ship_city_state": order.ship_city_state,
            "ship_zip": order.ship_zip,
            "resale_tax_id": order.resale_tax_id,
            "cert_required_ack": order.cert_required_ack,
            "cert_sending_ack": order.cert_sending_ack,
            "cert_on_file": order.cert_on_file,
            "signature_name": order.signature_name,
            "signature_date": order.signature_date,
            "terms_accepted": order.terms_accepted,
            "new_or_reorder": order.new_or_reorder,
            "account_status": order.account_status,
            "campaign": order.campaign,
            "po_number": order.po_number,
            "rep": order.rep,
            "order_written_by": order.order_written_by,
            "split_with": order.split_with,
            "sf_account_id": order.sf_account_id,
            "total_qty": total_qty,
            "total_amount": total_amount,
        },
        "items": [
            {
                "code": i.code,
                "style_name": i.style_name,
                "color": i.color,
                "qty_xs": i.qty_xs,
                "qty_sm": i.qty_sm,
                "qty_ml": i.qty_ml,
                "line_qty": i.line_qty,
                "unit_price": i.unit_price,
                "line_total": i.line_total,
            }
            for i in order_items
        ],
        # No card data reaches the template: the PDF shows the payment method
        # only, so the number/name/CVV never leave this request.
    }
    try:
        pdf_bytes = pdf_render.render_order_pdf(pdf_context)
    except Exception:
        logger.exception("PDF rendering failed for order attempt (season=%s)", payload.season)
        raise HTTPException(
            status_code=500,
            detail="The order could not be processed (PDF generation failed). Please try again.",
        )
    finally:
        pdf_context["payment"] = None  # drop card data reference immediately

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
    # the buyer order-copy is intentionally not sent from here; the buyer gets
    # their confirmation from the /admin review step instead. A background task
    # (like the conflict check below) so a slow or failed Gmail never blocks the
    # buyer's confirmation. The attachment is the in-memory, card-free PDF — so
    # it sends even if the disk save above failed. Admin sending also still
    # works on demand via POST /api/send-email.
    email_ctx = {
        "short_id": str(order.id)[:8],
        "season_code": order.season_code,
        "season_label": mapping.season_label(order.season_code),
        "buyer_name": order.buyer_name,
        "total_qty": total_qty,
        "total_amount": total_amount,
    }
    background.add_task(order_email.send_admin_copy, email_ctx, pdf_bytes, filename)

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
