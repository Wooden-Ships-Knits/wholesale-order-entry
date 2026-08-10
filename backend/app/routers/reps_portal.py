"""/api/reps-portal — read-only order monitoring for the sales reps.

A rep signs in, sees the orders that belong to them, and can do nothing else:
no emailing, no accept/decline, no PDFs. See
docs/superpowers/specs/2026-08-10-reps-monitoring-dashboard-design.md.

Deliberately NOT a reduced view of /admin. The admin row carries card name and
last 4, expiry, payment method, the nearby-stockist conflict verdict, Salesforce
ids and dollar totals; hiding those in the browser would still send every one of
them to the rep's machine. So the split is server-side: this router builds its
own row (`_rep_row`) that never reads the sensitive columns, and its own session
key, so a rep session is rejected by `require_admin` and vice versa.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.security import verify_password
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.sheets import client as sheets_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reps-portal")

# Its own key inside the shared signed cookie. Separate from admin's "admin"
# key on purpose: neither session can be mistaken for the other.
REP_SESSION_KEY = "rep"

# Who may sign in. A constant rather than the region/rep sheet because this is a
# security boundary — only these names get a session — and the sheet's Email tab
# also carries rows that are not reps. Adding a rep is a one-line change here;
# the name must match the sheet's Name column (column C) or their orders won't
# resolve (test_reps_portal asserts every name maps to an address).
REP_NAMES = (
    "Aviva Landin",
    "Denise Arnett",
    "Jason Hilsenrad",
    "Kitty Tally",
    "Michael Young",
    "Rande Cohen",
    "Vickie Wilde",
)

# A wrong name and a wrong password say the same thing.
_BAD_CREDENTIALS = "Incorrect name or password"

# Enough rows for a rep's whole season without letting one request read the
# entire table. Applied AFTER the ownership filter (see list_orders).
MAX_ROWS = 500


class RepLoginRequest(BaseModel):
    name: str
    password: str


def require_rep(request: Request) -> str:
    """Dependency guarding the rep routes. Returns the signed-in rep's name."""
    name = request.session.get(REP_SESSION_KEY)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Rep sign-in required"
        )
    return name


RepRequired = Depends(require_rep)


# ------------------------------------------------------------------ session

@router.get("/names")
def list_rep_names() -> dict:
    """The login dropdown. Unauthenticated — a login page has to show its own
    options — and it is only the roster, never an address."""
    return {"names": list(REP_NAMES)}


@router.post("/login")
def login(payload: RepLoginRequest, request: Request) -> dict:
    if not settings.reps_password_hash:
        logger.error("Rep login attempted but REPS_PASSWORD_HASH is not set")
        raise HTTPException(status_code=503, detail="Rep access is not configured")
    # The name comes from the browser, so it is checked against the roster here
    # rather than trusted — otherwise any string would become a session identity
    # and the ownership filter would run on it.
    if payload.name not in REP_NAMES:
        logger.warning("Rep login attempted with an unknown name")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS
        )
    if not verify_password(payload.password, settings.reps_password_hash):
        # Never log the attempted password.
        logger.warning("Failed rep login attempt for %s", payload.name)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS
        )
    request.session[REP_SESSION_KEY] = payload.name
    return {"ok": True, "name": payload.name}


@router.post("/logout")
def logout(request: Request) -> dict:
    # Pop, not clear: an admin signed in on the same browser keeps their session.
    request.session.pop(REP_SESSION_KEY, None)
    return {"ok": True}


@router.get("/session")
def session_state(request: Request) -> dict:
    """Lets the page decide between the login screen and the table."""
    name = request.session.get(REP_SESSION_KEY)
    return {"authenticated": bool(name), "name": name}


# ------------------------------------------------------------------- orders

def _signature_edited(o: Order) -> bool:
    """Did the buyer change the order before signing it?

    orig_* is the snapshot taken when the signing link first went out, so a null
    means nothing was ever sent for signature and there is nothing to compare.
    Computed here rather than in the browser so the dollar totals never have to
    be serialized to a rep.
    """
    return o.orig_total_qty is not None and (
        o.orig_total_qty != o.total_qty or o.orig_total_amount != o.total_amount
    )


def _rep_row(o: Order) -> dict:
    """The eleven columns of the rep dashboard, and nothing else.

    Every key here is deliberate; test_reps_portal pins the exact set so a later
    edit cannot quietly reintroduce card, conflict or Salesforce data. Three
    omissions worth naming:

      * no full order id — nothing on the page acts on an order, so the id that
        the admin routes accept never reaches a rep
      * no money — quantity is on the rep's column list, dollar totals are not
      * no card / conflict / certificate / Salesforce fields at all
    """
    return {
        "shortId": str(o.id)[:8],
        "createdAt": o.created_at.isoformat() if o.created_at else None,
        "seasonCode": o.season_code,
        "totalQty": o.total_qty,
        "shipWindow": o.ship_window,
        "accountName": o.account_name,
        "orderWrittenBy": o.order_written_by,
        "salesTerritory": o.sales_territory,
        "notes": o.notes,
        # Accept/decline as the office recorded it — read-only here.
        "status": o.status,
        "statusReason": o.status_reason,
        "statusAt": o.status_at.isoformat() if o.status_at else None,
        # Signature by emailed link, same three states the admin column shows:
        # not required (signed on the form) / awaiting / signed.
        "signatureRequested": _signature_requested(o),
        "signatureEmailSent": o.signature_requested_at is not None,
        "signatureEmail": o.signature_email,
        "signatureSignedAt": (
            o.signature_signed_at.isoformat() if o.signature_signed_at else None
        ),
        "signatureName": o.signature_name,
        "signatureEdited": _signature_edited(o),
        "origTotalQty": o.orig_total_qty,
    }


def _signature_requested(o: Order) -> bool:
    """Did this order ask to be signed by the buyer? False = signed on the form.

    signature_signed_at has to be part of the test: the token is nulled on
    signing, so a signed order can carry nothing else.
    """
    return bool(
        o.signature_email
        or o.signature_requested_at
        or o.signature_token
        or o.signature_signed_at
    )


def _awaiting_signature(o: Order) -> bool:
    """A signing link is outstanding: asked for, not yet signed."""
    return _signature_requested(o) and o.signature_signed_at is None


def _counts(orders: list[Order], now: datetime) -> dict:
    """The metric cards, over the rep's WHOLE book.

    Deliberately computed before the status filter: the cards are how a rep sees
    what is outstanding, so clicking "Accepted" must not zero out the other
    four. That is also why they are built here and not in the browser — once a
    status filter is applied the page only holds part of the book.

    `oldestAwaitingDays` is what makes the awaiting-signature count mean
    anything: three links out for two days is healthy, one out for three weeks
    is a lost order. Measured from when the link was sent where that is known,
    and from the order date otherwise.
    """
    awaiting = [o for o in orders if _awaiting_signature(o)]
    ages = [((now - (o.signature_requested_at or o.created_at)).days) for o in awaiting]
    return {
        "total": len(orders),
        "totalQty": sum(o.total_qty or 0 for o in orders),
        "awaitingSignature": len(awaiting),
        # The link exists but the email never left — the office has to send it.
        "signatureNotSent": sum(1 for o in awaiting if o.signature_requested_at is None),
        "oldestAwaitingDays": max(ages) if ages else None,
        "awaitingReview": sum(1 for o in orders if o.status == "submitted"),
        "accepted": sum(1 for o in orders if o.status == "accepted"),
        "declined": sum(1 for o in orders if o.status == "declined"),
    }


def _owns(o: Order, rep_email: str) -> bool:
    """Is this order the signed-in rep's?

    Delegates to the same function that routes the order email
    (rep_email_for_order): Written By is the authority, the Sales Territory
    owner is the fallback for customer-filled orders. Reusing it means the
    dashboard and the rep's inbox cannot disagree about whose order this is.
    """
    owner = sheets_client.rep_email_for_order(o.order_written_by, o.sales_territory)
    return bool(owner) and owner.casefold() == rep_email


@router.get("/orders")
def list_orders(
    rep_name: str = RepRequired,
    db: Session = Depends(get_db),
    status_filter: str | None = None,
    limit: int = Query(MAX_ROWS, ge=1, le=MAX_ROWS),
) -> dict:
    rep_email = sheets_client.rep_email_for_writer(rep_name)
    if not rep_email:
        # Fail closed. Without an address there is no way to tell this rep's
        # orders from anyone else's, and returning the unfiltered list would
        # hand one rep the whole customer book.
        logger.warning("No sheet email for signed-in rep %s — showing no orders", rep_name)
        return {
            "rep": rep_name,
            "orders": [],
            "counts": _counts([], datetime.now(timezone.utc)),
            "message": (
                "Your name isn't in the rep contact sheet yet, so no orders can "
                "be matched to you. Ask the office to add it."
            ),
        }

    # No SQL LIMIT and no SQL status filter. Ownership is a Google Sheet lookup
    # rather than a column, so a pre-filter cap would truncate the candidate set
    # and silently drop this rep's older orders; and the metric cards have to
    # count the whole book, which a WHERE on status would make impossible.
    stmt = select(Order).order_by(Order.created_at.desc())
    mine = [o for o in db.execute(stmt).scalars() if _owns(o, rep_email.casefold())]

    counts = _counts(mine, datetime.now(timezone.utc))
    if status_filter:
        mine = [o for o in mine if o.status == status_filter]

    return {
        "rep": rep_name,
        "orders": [_rep_row(o) for o in mine[:limit]],
        "counts": counts,
        "message": None,
    }
