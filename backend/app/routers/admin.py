"""/api/admin — order monitoring for the admin team.

Every route except login/session is behind require_admin. Order PDFs and tax
certificates live outside the web root and are streamed through here, never
served statically: they carry buyer contact details and tax IDs.
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import crypto
from app.admin.security import SESSION_KEY, AdminRequired, verify_password
from app.ai import conflict_reply
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.login_guard import LoginGuard, client_ip
from app.email import inbound, order_email
from app.pdf import render as pdf_render
from app.routers import orders
from app.routers.accounts import account_city_state
from app.salesforce import account_search
from app.salesforce import client as sf_client
from app.salesforce import mapping
from app.sheets import client as sheets_client
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

VALID_STATUSES = {"accepted", "declined"}

# Failed-attempt throttle for the admin password.
guard = LoginGuard("admin")


class LoginRequest(BaseModel):
    password: str


class StatusRequest(BaseModel):
    status: str
    reason: str = Field("", max_length=1000)


class ConflictResolutionRequest(BaseModel):
    # The rep either cleared the inquiry or confirmed a genuine territory
    # conflict; anything else is a 422. note is optional free text.
    outcome: Literal["cleared", "real_conflict"]
    note: str = Field("", max_length=1000)


# ------------------------------------------------------------------ session

@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    if not settings.admin_password_hash:
        logger.error("Admin login attempted but ADMIN_PASSWORD_HASH is not set")
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    # Throttle before verifying, so a locked-out caller cannot tell a correct
    # guess from a wrong one. One account here, so the identity is a constant —
    # the per-identity counter is what survives an attacker rotating addresses.
    ip = client_ip(request)
    guard.check(ip, "admin")
    if not verify_password(payload.password, settings.admin_password_hash):
        # Never log the attempted password.
        guard.record_failure(ip, "admin")
        logger.warning("Failed admin login attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password"
        )
    guard.record_success(ip, "admin")
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
        # Buyer-selected ship window. Editable from /admin (the season is not —
        # changing it would invalidate every line item's price book).
        "shipWindow": o.ship_window,
        "accountName": o.account_name,
        # Internal Use "Order written by" — a rep-filled order records who wrote
        # it; a customer-filled one leaves it empty.
        "orderWrittenBy": o.order_written_by,
        "orderCopyEmail": o.order_copy_email,
        "salesTerritory": o.sales_territory,
        # Account rank at order time; a new account has none yet, so show the
        # rank it will be created with (Rank C).
        "rank": o.rank or (mapping.RANK_NEW_ACCOUNT if o.is_new_account else None),
        # Rep email for this order: whoever wrote it, else the territory's
        # lead rep. Used as the tax-cert CC. Null when neither resolves.
        "repEmail": sheets_client.rep_email_for_order(o.order_written_by, o.sales_territory),
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
        # Buyer signature by emailed link. Sent → waiting → signed. The token
        # itself is never exposed: it is a credential, and /admin doesn't need
        # it to show state or to re-draft the email.
        # Did this order ask to be signed by the buyer? False = the form was
        # signed on the spot, so the admin column has nothing to chase.
        "signatureRequested": bool(
            o.signature_email
            or o.signature_requested_at
            or o.signature_token
            or o.signature_signed_at
        ),
        # True only once the email actually left (see orders._send_signature_request);
        # a requested-but-unsent order shows as still needing to go out.
        "signatureEmailSent": o.signature_requested_at is not None,
        # The link exists but is deliberately unsent, waiting on the conflict
        # inquiry. Without this the cell reads "Not sent — send it manually",
        # which is the opposite of what the team should do.
        "signatureHeldForConflict": (
            orders.signature_on_conflict_hold(o)
            and bool(o.signature_token)
            and o.signature_requested_at is None
        ),
        "signatureEmail": o.signature_email,
        # A usable link is out there right now, so admin edits are blocked
        # (_reject_if_awaiting_signature). The token itself is never sent.
        "signatureLinkLive": bool(o.signature_token) and o.signature_signed_at is None,
        "signatureSignedAt": (
            o.signature_signed_at.isoformat() if o.signature_signed_at else None
        ),
        "signatureName": o.signature_name,
        # Non-null only once a buyer edited the order through the sign link —
        # the pre-edit totals, so the change is visible instead of silent.
        "origTotalQty": o.orig_total_qty,
        "origTotalAmount": (
            float(o.orig_total_amount) if o.orig_total_amount is not None else None
        ),
        # Recorded outcome of the conflict inquiry (null = still waiting).
        "conflictResolution": o.conflict_resolution,
        "conflictResolvedAt": (
            o.conflict_resolved_at.isoformat() if o.conflict_resolved_at else None
        ),
        "conflictResolutionNote": o.conflict_resolution_note,
        # Classifier's suggested outcome from a captured reply (null = none yet).
        "conflictAiOutcome": o.conflict_ai_outcome,
        "conflictAiConfidence": (
            float(o.conflict_ai_confidence) if o.conflict_ai_confidence is not None else None
        ),
        "conflictAiReason": o.conflict_ai_reason,
        "conflictAiAt": o.conflict_ai_at.isoformat() if o.conflict_ai_at else None,
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


def _reject_if_awaiting_signature(order: Order, what: str) -> None:
    """Block admin edits while the buyer holds a live signing link.

    A live token means someone can change the lines and sign at any moment. The
    dangerous case is Accept: it pushes the CURRENT lines to Salesforce as a
    Kugamon Draft and is idempotent on sf_order_id, so if the buyer then signs
    with different quantities the two systems disagree permanently and nothing
    ever reconciles them. The ship window is the milder version of the same
    race — last write wins, silently — but it is what the buyer is agreeing to,
    so it stays frozen too.

    Account relink used to be blocked here as well and no longer is (see
    relink_account): correcting the store touches nothing in Salesforce until
    Accept, and blocking it meant a mis-linked order could only be fixed by
    revoking the buyer's link.

    The escape hatch is POST /orders/{id}/cancel-signature: revoke the link and
    the order is ordinary again. That is deliberate rather than a force flag —
    the admin has to take the buyer's ability to sign away, not just override it.
    """
    if order.signature_token and not order.signature_signed_at:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A signature request is outstanding for this order — {what} "
                "until the buyer signs, or cancel the signing link first."
            ),
        )


def _account_exists(order: Order) -> bool | None:
    """Does Salesforce already have a store with this order's account name?
    None when it can't be determined (no name, or the lookup failed) — the UI
    then falls back to the buyer's answer and marks it unverified."""
    name = (order.account_name or "").strip()
    if not name:
        return None
    try:
        return name.casefold() in sf_client.existing_account_names([name])
    except Exception:
        logger.exception("Account-name check failed for order %s", str(order.id)[:8])
        return None


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
    except sf_client.SalesforceReadOnly as exc:
        # A dev environment, not a failure — 400 so the admin sees the reason
        # rather than a "Salesforce is broken" 502.
        raise HTTPException(status_code=400, detail=str(exc))
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
    _reject_if_awaiting_signature(order, "it can't be accepted or declined")
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
    # No buyer email on Accept/Decline yet — the only automatic buyer mail is
    # the order copy at submit. A confirmation (and especially a decline) is a
    # relationship message the team words itself via the email draft modal.
    return _row(order)


@router.post("/orders/{order_id}/conflict-resolution", dependencies=[AdminRequired])
def set_conflict_resolution(
    order_id: str,
    payload: ConflictResolutionRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Record how a conflict inquiry ended so the row closes instead of sitting
    at "waiting for the response". A local status stamp — Salesforce is not
    touched — with one side effect: clearing the conflict releases a signing
    link that was held back for it.

    "cleared" means the rep says this store may proceed, so the buyer can now
    be asked to sign. "real_conflict" sends nothing: the order is not going
    ahead, and mailing the buyer a signing link would invite them to commit to
    an order the team is about to decline. The team can still send it by hand.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    was_held = orders.signature_on_conflict_hold(order)
    order.conflict_resolution = payload.outcome
    order.conflict_resolution_note = payload.note or None
    order.conflict_resolved_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Order %s conflict marked %s", str(order.id)[:8], payload.outcome)

    # Only for a link that never went out: signature_requested_at is stamped on
    # a successful send, so a re-cleared conflict can't re-mail a buyer who was
    # already asked.
    if (
        was_held
        and payload.outcome == "cleared"
        and order.signature_token
        and order.signature_requested_at is None
    ):
        logger.info(
            "Order %s conflict cleared — releasing the held signing link", str(order.id)[:8]
        )
        background.add_task(orders._send_signature_request, order.id)
    return _row(order)


@router.post("/poll-replies", dependencies=[AdminRequired])
def poll_replies(db: Session = Depends(get_db)) -> dict:
    """Capture new inbound conflict replies, then classify them into suggestions.
    Safe to call repeatedly (and from a cron): both steps no-op when IMAP /
    OpenAI are unconfigured, and captured replies are deduped by Message-ID."""
    captured = inbound.run_poll(db)
    suggested = conflict_reply.run_classify(db)
    return {"captured": captured, "suggested": suggested}
@router.get("/accounts/suggest", dependencies=[AdminRequired])
def admin_suggest_accounts(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(10, ge=1, le=25),
) -> dict:
    """Store-name search for the admin's account picker.

    Richer than the buyer-facing one and NOT rank-filtered: an admin picking
    between nine "SCOUT & MOLLY'S" locations needs the city and territory to
    choose, and may legitimately need to link an order to a store the buyer
    lookup hides (inactive, no-booking). This route is behind AdminRequired.
    """
    hits = account_search.search(sf_client.account_search_index(), q, limit)
    return {
        "suggestions": [
            {
                "accountId": r["Id"],
                "name": r.get("Name"),
                "cityState": account_city_state(r),
                "rank": r.get(mapping.RANK),
                "salesTerritory": r.get(mapping.SALES_TERRITORY),
            }
            for r in hits
        ]
    }


class AccountLinkRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=255)
    # Salesforce Account Id when a suggestion was picked; null when the admin
    # typed a name that matches nothing (i.e. it really is a new store).
    account_id: str | None = Field(None, min_length=15, max_length=18)


@router.post("/orders/{order_id}/account", dependencies=[AdminRequired])
def relink_account(order_id: str, payload: AccountLinkRequest, db: Session = Depends(get_db)) -> dict:
    """Correct which store an order belongs to.

    Reps can't always find the right account — a franchise like Scout & Molly
    has one row per location and the exact-name lookup finds none of them — so
    orders arrive attached to the wrong store or to none. This is where that
    gets fixed, before the order reaches Salesforce.

    Territory, rank and special instructions are account attributes copied onto
    the order at submit, so they follow the new link; leaving them would mean an
    order that reads "Nashville" while routing to the Midwest rep. Addresses are
    NOT touched — the rep entered where it actually ships, which is order data.

    Deliberately NOT frozen while a signing link is live, unlike Accept and the
    ship window (2026-08-06). Nothing here reaches Salesforce — that happens on
    Accept — so the worst case is a buyer holding an open tab that still names
    the old store; the sign page reads account_name live, so a reload shows the
    corrected one. Accept stays frozen because it pushes the current lines as a
    Kugamon Draft and can never be reconciled if the buyer then signs different
    quantities.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    # After Accept the order exists in Salesforce under a specific account;
    # rewriting it here would only desync the two.
    if order.status != "submitted":
        raise HTTPException(
            status_code=409,
            detail=f"This order is already {order.status} — its account can no longer be changed.",
        )

    before = (order.account_name, order.sf_account_id)

    # include_excluded: the admin picker deliberately offers inactive / OOB /
    # no-marketing stores, so resolving the pick has to see them too. Filtering
    # here made such an account look absent from Salesforce, and the order was
    # silently downgraded to "new" with its territory and rank wiped.
    typed = payload.account_name.strip()
    if payload.account_id:
        records = sf_client.find_accounts(account_id=payload.account_id, include_excluded=True)
    else:
        # No id means the admin typed rather than picked — but a typed name can
        # still BE an account. Store names are unique in this org, so resolve it
        # by name before concluding the store is new; otherwise correcting a
        # name by hand would silently drop the link, territory and rank.
        records = sf_client.find_accounts(name=typed, include_excluded=True)
        if len(records) > 1:
            raise HTTPException(
                status_code=409,
                detail=f'Several accounts are named "{typed}" — pick one from the suggestions instead.',
            )

    if records:
        acct = mapping.map_account(records[0])
        order.account_name = acct["name"] or typed
        order.sf_account_id = acct["accountId"]
        order.sales_territory = acct.get("salesTerritory")
        order.rank = acct.get("rank")
        order.special_instructions = acct.get("specialInstructions")
    elif payload.account_id:
        # An id was given but Salesforce no longer returns it — don't silently
        # fall back to "new store", the admin meant to link something specific.
        raise HTTPException(status_code=404, detail="That Salesforce account could not be loaded.")
    else:
        # Genuinely not in Salesforce: a new store. Clearing the id makes the
        # New account column say Yes and brings back the Create account button;
        # territory/rank/instructions belonged to the old link, so they go too.
        order.account_name = typed
        order.sf_account_id = None
        order.sales_territory = None
        order.rank = None
        order.special_instructions = None

    db.commit()
    logger.info(
        "Order %s account relinked: %r/%s -> %r/%s",
        str(order.id)[:8], before[0], before[1], order.account_name, order.sf_account_id,
    )
    return _row(order, _account_exists(order))


class ShipWindowRequest(BaseModel):
    ship_window: str = Field(min_length=1, max_length=120)


@router.get("/orders/{order_id}/ship-windows", dependencies=[AdminRequired])
def order_ship_windows(order_id: str, db: Session = Depends(get_db)) -> dict:
    """Ship windows the admin may choose for this order — the live list for the
    order's own season, so a window that has sold out is no longer offered."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"shipWindows": sheets_client.list_ship_windows(order.season_code)}


@router.post("/orders/{order_id}/ship-window", dependencies=[AdminRequired])
def set_ship_window(
    order_id: str, payload: ShipWindowRequest, db: Session = Depends(get_db)
) -> dict:
    """Change an order's ship window.

    Only the window: the season stays fixed because prices and Salesforce
    product ids were resolved from that season's price book at submit, so
    changing it would leave every line item priced against the wrong book.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    # Once accepted the window is on the Kugamon order in Salesforce; editing
    # here afterwards would leave the two disagreeing.
    if order.status != "submitted":
        raise HTTPException(
            status_code=409,
            detail=f"This order is already {order.status} — its ship window can no longer be changed.",
        )
    _reject_if_awaiting_signature(order, "its ship window can't be changed")

    window = payload.ship_window.strip()
    # Validate against the season's live list so a typo can't reach Salesforce.
    # If the sheet is unreachable the list comes back empty — allow the edit
    # rather than block the admin on an outage.
    allowed = sheets_client.list_ship_windows(order.season_code)
    if allowed and window not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f'"{window}" is not an available ship window for {order.season_code}.',
        )

    before = order.ship_window
    order.ship_window = window
    db.commit()
    logger.info("Order %s ship window: %r -> %r", str(order.id)[:8], before, window)
    return _row(order, _account_exists(order))


@router.post("/orders/{order_id}/cancel-signature", dependencies=[AdminRequired])
def cancel_signature(order_id: str, db: Session = Depends(get_db)) -> dict:
    """Revoke an outstanding signing link so the order can be worked on again.

    For the ordinary case of a buyer who never responds: the team needs to
    proceed, and _reject_if_awaiting_signature blocks them until the token is
    gone. Revoking makes the buyer's link 404 immediately, so it is the admin
    consciously taking away their ability to sign rather than editing behind
    their back — which is the whole reason the guard exists.

    signature_requested_at is kept: the request DID happen, and erasing it
    would lose the record of what was asked of the buyer and when.
    """
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.signature_signed_at is not None:
        raise HTTPException(
            status_code=409, detail="This order is already signed — there is no live link."
        )
    order.signature_token = None
    order.signature_token_expires_at = None
    db.commit()
    logger.info("Signing link revoked for order %s", str(order.id)[:8])
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
    except sf_client.SalesforceReadOnly as exc:
        raise HTTPException(status_code=400, detail=str(exc))
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
    """HTTP wrapper over pdf_render.safe_output_path (shared with /reps)."""
    try:
        return pdf_render.safe_output_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")


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
