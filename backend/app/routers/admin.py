"""/api/admin — order monitoring for the admin team.

Every route except login/session is behind require_admin. Order PDFs and tax
certificates live outside the web root and are streamed through here, never
served statically: they carry buyer contact details and tax IDs.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import crypto
from app.admin.security import SESSION_KEY, AdminRequired, verify_password
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.pdf import render as pdf_render
from app.salesforce import client as sf_client
from app.salesforce import mapping
from app.sheets import client as sheets_client
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

VALID_STATUSES = {"accepted", "declined"}


class LoginRequest(BaseModel):
    password: str


class StatusRequest(BaseModel):
    status: str
    reason: str = Field("", max_length=1000)


# ------------------------------------------------------------------ session

@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    if not settings.admin_password_hash:
        logger.error("Admin login attempted but ADMIN_PASSWORD_HASH is not set")
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if not verify_password(payload.password, settings.admin_password_hash):
        # Never log the attempted password.
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
        )
    request.session[SESSION_KEY] = True
    return {"ok": True}


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/session")
def session_state(request: Request) -> dict:
    """Lets the page decide between the login screen and the table."""
    return {"authenticated": bool(request.session.get(SESSION_KEY))}


# ------------------------------------------------------------------ orders

def _row(o: Order, account_exists: bool | None = None) -> dict:
    return {
        # Does a Salesforce account with this store name already exist? This —
        # not the buyer's "is this your first order?" answer — drives the New
        # account column. None = the Salesforce lookup didn't run or failed, so
        # the UI falls back to the buyer's answer and marks it unverified.
        "accountExists": account_exists,
        "id": str(o.id),
        "shortId": str(o.id)[:8],
        "createdAt": o.created_at.isoformat() if o.created_at else None,
        "seasonCode": o.season_code,
        "accountName": o.account_name,
        "orderCopyEmail": o.order_copy_email,
        "salesTerritory": o.sales_territory,
        # Account rank at order time; a new account has none yet, so show the
        # rank it will be created with (Rank C).
        "rank": o.rank or (mapping.RANK_NEW_ACCOUNT if o.is_new_account else None),
        # Lead rep email for the territory (tax-cert CC / conflict recipient);
        # null when territory is empty or has no rep row.
        "repEmail": sheets_client.rep_email_for_territory(o.sales_territory),
        "specialInstructions": o.special_instructions,
        "shipEmail": o.ship_email,
        "totalQty": o.total_qty,
        "totalAmount": float(o.total_amount) if o.total_amount is not None else None,
        # null = unanswered / not yet checked. The UI must not render these as "No".
        "isNewAccount": o.is_new_account,
        "hasConflict": o.has_conflict,
        # Persistent "Sent ✓" state for the admin email buttons.
        "conflictEmailSent": o.conflict_email_sent_at is not None,
        "taxCertEmailSent": o.tax_cert_email_sent_at is not None,
        "hasCertificate": bool(o.cert_filename),
        # Salesforce Account link. sfAccountId may come from the buyer's own
        # lookup at submit time, so it does NOT mean an account was created —
        # only sfAccountCreated does.
        "sfAccountId": o.sf_account_id,
        "sfAccountCreated": o.sf_account_created_at is not None,
        # Kugamon order pushed on Accept: id + auto-number (null = not pushed).
        "sfOrderId": o.sf_order_id,
        "sfOrderNumber": o.sf_order_number,
        # Payment: method tells the team which Kugamon record type to pick.
        # Never the card number — that only exists inside the encrypted admin
        # PDF, served by the ?full=1 route.
        "paymentMethod": o.payment_method,
        "approvalBeforeCharge": o.approval_before_charge,
        "cardName": o.card_name,
        "cardLast4": o.card_last4,
        "cardExp": o.card_exp,
        "hasCardCopy": o.card_pdf_enc is not None,
        "notes": o.notes,
        "status": o.status,
        "statusReason": o.status_reason,
        "statusAt": o.status_at.isoformat() if o.status_at else None,
    }


def _purge_expired_card_copies(db: Session) -> None:
    """Drop card copies older than CARD_RETENTION_DAYS.

    Accept/Decline already purges; this catches orders that were never decided,
    so a card can't linger indefinitely. Runs on the admin order list rather
    than a scheduler — the page is opened often enough, and it keeps the
    deployment to the same three containers.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.card_retention_days)
    result = db.execute(
        update(Order)
        .where(Order.card_pdf_enc.is_not(None), Order.created_at < cutoff)
        .values(card_pdf_enc=None)
    )
    if result.rowcount:
        db.commit()
        logger.info("Purged %d expired card copies", result.rowcount)


@router.get("/orders", dependencies=[AdminRequired])
def list_orders(
    db: Session = Depends(get_db),
    status_filter: str | None = None,
    limit: int = 100,
) -> dict:
    _purge_expired_card_copies(db)

    stmt = select(Order).order_by(Order.created_at.desc()).limit(min(limit, 500))
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    orders = list(db.execute(stmt).scalars())

    # One batched Salesforce lookup for every store name on the page: a name
    # that exists is an existing stockist, one that doesn't is a new account.
    # On failure every row gets None ("unverified") rather than a wrong verdict
    # — a false "already exists" would hide the Create account button.
    try:
        existing = sf_client.existing_account_names([o.account_name for o in orders])
    except Exception:
        logger.exception("Account-name lookup failed — New account column unverified")
        existing = None

    def exists(o: Order) -> bool | None:
        if existing is None or not (o.account_name or "").strip():
            return None
        return o.account_name.strip().casefold() in existing

    return {"orders": [_row(o, exists(o)) for o in orders]}


def _push_order_to_salesforce(order: Order) -> None:
    """Create the Kugamon Draft order for an accepted order. Sets sf_order_id /
    sf_order_number on success; raises HTTPException (surfaced to the admin) on
    any problem. Idempotent: a re-push is a no-op once sf_order_id is set."""
    if order.sf_order_id:
        return  # already pushed — don't create a second order
    if not order.sf_account_id:
        raise HTTPException(
            status_code=400,
            detail="This order has no Salesforce account yet. Create the account first, then Accept.",
        )
    # A new-account order can still carry an sf_account_id from the buyer's own
    # lookup. Pushing on that id would file the order under whatever store they
    # searched for, which may not be theirs. Gate on whether Salesforce actually
    # has this store — the same question the New account column asks — not on
    # the buyer's answer, which would block legitimate existing accounts.
    if not order.sf_account_created_at and (order.account_name or "").strip():
        try:
            known = sf_client.existing_account_names([order.account_name])
            store_exists = order.account_name.strip().casefold() in known
        except Exception:
            # Can't tell — don't block on a guess; the sf_account_id check above
            # still applies.
            logger.exception("Account-name check failed for order %s", str(order.id)[:8])
            store_exists = True
        if not store_exists:
            raise HTTPException(
                status_code=400,
                detail=(
                    f'No Salesforce account named "{order.account_name}" exists. '
                    "Click 'Create account' first — accepting now would file the order "
                    "under an account the buyer looked up, which is a different store."
                ),
            )
    pricebook_id = sf_client.get_wholesale_pricebook_id(order.season_code)
    if not pricebook_id:
        raise HTTPException(
            status_code=502, detail=f"No wholesale price book found for {order.season_code}."
        )
    lines = mapping.build_sales_order_lines(order)
    if not lines:
        raise HTTPException(status_code=400, detail="This order has no line items to push.")

    header = mapping.build_sales_order_header(
        order,
        pricebook_id,
        sales_territory=sf_client.match_order_territory(order.sales_territory),
        campaign_id=sf_client.campaign_id_for(order.campaign),
    )
    try:
        so_id, so_number = sf_client.create_sales_order(header, lines)
    except Exception as exc:  # header/line rejection, permission, etc.
        logger.exception("Salesforce order push failed for order %s", str(order.id)[:8])
        raise HTTPException(status_code=502, detail=f"Salesforce order create failed: {exc}")

    order.sf_order_id = so_id
    order.sf_order_number = so_number
    logger.info("Pushed order %s to Salesforce as %s", str(order.id)[:8], so_number or so_id)


@router.post("/orders/{order_id}/status", dependencies=[AdminRequired])
def set_status(order_id: str, payload: StatusRequest, db: Session = Depends(get_db)) -> dict:
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="status must be accepted or declined")
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    # Accept = push the order into Salesforce (Kugamon Draft). If the push
    # fails, raise BEFORE changing status so the order stays actionable and the
    # team can fix the cause (e.g. missing account) and click Accept again.
    if payload.status == "accepted":
        _push_order_to_salesforce(order)
    order.status = payload.status
    order.status_reason = payload.reason or None
    order.status_at = datetime.now(timezone.utc)
    # The card copy exists only for the review step. Once the order is decided
    # the monitoring team has keyed it into Salesforce (or never will), so drop
    # it in the same commit — cardholder data is kept no longer than needed.
    if order.card_pdf_enc is not None:
        order.card_pdf_enc = None
        logger.info("Card copy purged for order %s (%s)", str(order.id)[:8], payload.status)
    db.commit()
    logger.info("Order %s marked %s", str(order.id)[:8], payload.status)
    return _row(order)


@router.post("/orders/{order_id}/create-account", dependencies=[AdminRequired])
def create_account(order_id: str, db: Session = Depends(get_db)) -> dict:
    """Create the Salesforce Business Account for a new-account order.

    Idempotent: refuses if an account was already created here, so a double-click
    never makes two accounts. Live-org write — any Salesforce rejection
    (duplicate/validation/permission) is surfaced, not swallowed.

    Guards on sf_account_created_at, NOT sf_account_id: the id is also set at
    submit time from the buyer's lookup, so guarding on it refused creation for
    every order whose buyer searched for their store first.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.sf_account_created_at:
        raise HTTPException(
            status_code=409,
            detail=f"A Salesforce account was already created for this order ({order.sf_account_id}).",
        )
    if not order.is_new_account:
        raise HTTPException(status_code=400, detail="This order is not marked as a new account.")
    if not (order.account_name or "").strip():
        raise HTTPException(status_code=400, detail="This order has no account name to create.")

    payload = mapping.build_account_create_payload(order)
    try:
        account_id = sf_client.create_account(payload)
    except Exception as exc:  # duplicate rule, validation rule, permission, etc.
        logger.exception("Salesforce account create failed for order %s", str(order.id)[:8])
        raise HTTPException(status_code=502, detail=f"Salesforce create failed: {exc}")

    order.sf_account_id = account_id
    order.sf_account_created_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Created SF account %s for order %s", account_id, str(order.id)[:8])
    return _row(order)


# ------------------------------------------------------------------ files

def _safe_output_path(filename: str) -> Path:
    """Resolve a filename inside pdf_output_dir, refusing anything that escapes it."""
    base = Path(settings.pdf_output_dir).resolve()
    path = (base / filename).resolve()
    if not path.is_relative_to(base):
        logger.warning("Blocked path traversal attempt: %r", filename)
        raise HTTPException(status_code=400, detail="Invalid file")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return path


@router.get("/orders/{order_id}/pdf", dependencies=[AdminRequired])
def download_pdf(order_id: str, full: bool = False, db: Session = Depends(get_db)):
    """The order PDF. `full=1` serves the admin copy showing the whole card
    number, for keying into Salesforce; it is decrypted per request, streamed
    from memory, and never written to disk. Falls back to the masked copy once
    the card has been purged (on Accept/Decline, or by the retention sweep)."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )

    if full and order.card_pdf_enc:
        try:
            pdf_bytes = crypto.decrypt(order.card_pdf_enc)
        except Exception:
            logger.exception("Could not decrypt the admin card copy for order %s", str(order.id)[:8])
            raise HTTPException(
                status_code=500,
                detail="The card copy for this order could not be opened. Check CARD_ENCRYPTION_KEY.",
            )
        # PCI expects an audit trail for access to cardholder data. Log the
        # access, never the data.
        logger.info("ADMIN CARD ACCESS: full card copy served for order %s", str(order.id)[:8])
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                # Never let a card copy sit in a browser or proxy cache.
                "Cache-Control": "no-store, private",
            },
        )

    # inline → the browser renders it in the tab instead of downloading.
    return FileResponse(
        _safe_output_path(filename),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.get("/orders/{order_id}/certificate", dependencies=[AdminRequired])
def download_certificate(order_id: str, db: Session = Depends(get_db)) -> FileResponse:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.cert_filename:
        raise HTTPException(status_code=404, detail="No certificate for this order")
    # PDFs and images render inline; browsers fall back to downloading anything
    # they can't display, so this is safe for every allowed cert type.
    return FileResponse(
        _safe_output_path(order.cert_filename),
        filename=order.cert_filename,
        content_disposition_type="inline",
    )
