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
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Order, Prospect, ProspectMark
from app.db.session import get_db
from app.login_guard import LoginGuard, client_ip
from app.pdf import render as pdf_render
from app.reps_auth import REP_NAMES, normalize_name, resolve_name, verify_rep
from app.salesforce import client as sf_client
from app.salesforce import mapping
from app.sheets import client as sheets_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reps-portal")

# Its own key inside the shared signed cookie. Separate from admin's "admin"
# key on purpose: neither session can be mistaken for the other.
REP_SESSION_KEY = "rep"

# The roster and the per-rep hashes live in app.reps_auth; re-exported here
# because REP_NAMES is what this router's routes are about.

# A wrong name and a wrong password say the same thing.
_BAD_CREDENTIALS = "Incorrect name or password"

# Failed-attempt throttle. Keyed on the rep's name as well as the caller's
# address, because the sign-in name is a rep's first name — anyone who has met
# the sales team already knows which accounts are worth attacking.
guard = LoginGuard("rep")

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
    """The roster, and only the roster — never an address.

    The sign-in page stopped calling this on 2026-08-11, when the name became a
    text box; it is kept for the office (checking who is set up) and stays
    unauthenticated because it says nothing a sign-in attempt would not.
    """
    return {"names": list(REP_NAMES)}


@router.post("/login")
def login(payload: RepLoginRequest, request: Request) -> dict:
    if not settings.reps_password_hashes.strip():
        logger.error("Rep login attempted but REPS_PASSWORD_HASHES is not set")
        raise HTTPException(status_code=503, detail="Rep access is not configured")
    # Checked before the password, so a locked-out caller cannot tell a correct
    # guess from a wrong one.
    ip = client_ip(request)
    # Reps type their first name, so the typed text is resolved to the roster
    # name before anything else uses it. That name — not what was typed — is
    # what the throttle counts, what the password is checked against and what
    # goes in the session, so "aviva", "AVIVA" and "Aviva Landin" are one
    # identity throughout. An unknown name resolves to None and is failed
    # below, after the throttle check, like any other bad credential.
    name = resolve_name(payload.name)
    identity = name or normalize_name(payload.name)
    guard.check(ip, identity)
    # Password is checked AGAINST THE NAMED REP, not against a shared secret:
    # the name is the identity the whole dashboard is filtered by, so a right
    # password under someone else's name has to fail. verify_rep also re-checks
    # the roster, so a string the browser invents never becomes a session.
    if not name or not verify_rep(name, payload.password, settings.reps_password_hashes):
        # Never log the attempted password. The name is safe to log and is the
        # only thing that makes repeated failures diagnosable.
        guard.record_failure(ip, identity)
        logger.warning("Failed rep login attempt for %r", payload.name)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS
        )
    guard.record_success(ip, identity)
    request.session[REP_SESSION_KEY] = name
    logger.info("Rep signed in: %s", name)
    return {"ok": True, "name": name}


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
        # The Order ID cell links to the order PDF, so the page needs the real
        # id. It is a lookup key, not a capability: /reps-portal/orders/{id}/pdf
        # re-checks ownership, so holding another rep's id gets you a 404.
        "id": str(o.id),
        "shortId": str(o.id)[:8],
        "createdAt": o.created_at.isoformat() if o.created_at else None,
        "seasonCode": o.season_code,
        "totalQty": o.total_qty,
        "shipWindow": o.ship_window,
        "accountName": o.account_name,
        # Order value at the prices in force when it was submitted. Added
        # 2026-08-10 at the business's request — v1 deliberately sent a rep no
        # money at all. The PRE-signature snapshot (orig_total_amount) is still
        # withheld: signatureEdited carries that comparison instead.
        "totalAmount": float(o.total_amount) if o.total_amount is not None else None,
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


@router.get("/orders/{order_id}/pdf")
def download_pdf(
    order_id: str,
    rep_name: str = RepRequired,
    db: Session = Depends(get_db),
) -> FileResponse:
    """The buyer-facing order PDF, for one of THIS rep's own orders.

    Always the masked copy — card shown as •••• last4. There is deliberately no
    `full=1` here: the admin copy carrying the whole card number exists for the
    monitoring team to key into Kugamon, and nothing on this page needs it.

    An order the signed-in rep does not own returns 404, not 403: a rep should
    not be able to probe which order ids exist outside their own book. Same
    reason the ownership check comes before the file is even named.
    """
    rep_email = sheets_client.rep_email_for_writer(rep_name)
    order = db.get(Order, order_id)
    if order is None or not rep_email or not _owns(order, rep_email.casefold()):
        logger.info("Rep %s was refused order %s", rep_name, str(order_id)[:8])
        raise HTTPException(status_code=404, detail="Order not found")

    filename = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )
    try:
        path = pdf_render.safe_output_path(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")

    # inline → the browser renders it in the tab instead of downloading.
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


# ----------------------------------------------------------------- prospects

def _prospect_row(p: Prospect, marked: bool) -> dict:
    """One prospect, as the rep page needs it.

    A SEPARATE serializer from _rep_row for the same reason that one is
    separate from admin's: a shared one accretes fields, and this page must
    stay incapable of emitting an order's value or card state.

    `matchedAccount` / `matchedBy` are deliberately NOT here — they are the
    sweep's own bookkeeping about which rule fired, of no use to a rep.
    """
    return {
        "id": p.osm_id,  # stable across re-sweeps; the row uuid is not shown
        "storeName": p.store_name,
        "latitude": float(p.latitude) if p.latitude is not None else None,
        "longitude": float(p.longitude) if p.longitude is not None else None,
        "city": p.city,
        "address": p.address,
        "state": p.state,
        "website": p.website,
        "phone": p.phone,
        # From the OSM email / contact:email tag. Often the only way to reach a
        # small shop that has no website.
        "email": p.email,
        "rating": float(p.rating) if p.rating is not None else None,
        "reviewCount": p.review_count,
        "womenswear": p.womenswear,
        "potentialConflict": p.potential_conflict,
        # Internal by design: reps are told which stockist is nearby (they get
        # the same in the conflict email); customers never are.
        "nearestStockist": p.nearest_stockist,
        "distanceMiles": float(p.distance_miles) if p.distance_miles is not None else None,
        "driveMinutes": p.drive_minutes,
        "marked": marked,
        # --- the assessment (app/prospects/assess.py) ------------------------
        # The answer only, not the measurements behind it. A rep is deciding
        # whether to make a call, and `for_the_rep` is the sentence written for
        # exactly that; brand_count and knitwear_share are how the verdict was
        # reached, which is an audit question and belongs on a page that can
        # show its working.
        #
        # All seven are NULL until assess_pending has paid for the row, and the
        # page needs to tell "nobody has looked at this yet" from "somebody
        # looked and it is weak" -- so they are always PRESENT and null, never
        # absent.
        "verdict": p.verdict,
        "confidence": p.confidence,
        "forTheRep": p.for_the_rep,
        "reasons": p.reasons,
        "against": p.against,
        # judge.check()'s findings -- an invented brand, or a verdict that
        # breaks a hard rule. The only field that says "do not trust this row",
        # so withholding it puts an unchecked answer in front of a rep with
        # nothing to mark it as one.
        "problems": p.problems,
        "assessedAt": p.assessed_at.isoformat() if p.assessed_at else None,
    }


def _stockists(rep_name: str) -> list[dict]:
    """The signed-in rep's current stores, LIVE from Salesforce, with coordinates.

    SCOPED BY THE TERRITORY LABEL naming the rep. Salesforce labels follow
    "Region - Owner" ("Midwest - Aviva Landin", "FL - House", "Majors - US"),
    so a rep owns exactly those whose label carries their name. A label naming
    nobody — House, or a bare region — is house business and belongs to no rep,
    which is why those accounts appear on nobody's map.

    Matched on the LABEL rather than through the reps email sheet because
    Salesforce carries 41 territory values and the sheet only 12; the sheet
    would silently hide every account filed under one of the other 29.

    Not read from the prospects table even though it carries a `status`
    column: that label only means "this OSM shop matched an account", and OSM
    holds barely a twentieth of the book — drawing grey dots from it would show
    a handful of stores instead of all of them. Salesforce is the authority for
    who we already sell to, so the map asks it every time.

    Accounts without coordinates cannot be plotted and are skipped.
    """
    name = (rep_name or "").strip()
    if not name:
        return []
    excluded = "','".join(mapping.EXCLUDED_RANKS)
    safe = name.replace("\\", "\\\\").replace("'", r"\'").replace("%", r"\%")
    q = (
        "SELECT Id, Name, SalesTerritory__c, ShippingLatitude, ShippingLongitude "
        "FROM Account "
        f"WHERE SalesTerritory__c LIKE '%{safe}%' "
        f"AND (Rank__c = null OR Rank__c NOT IN ('{excluded}')) "
        "AND ShippingLatitude != null AND ShippingLongitude != null"
    )
    try:
        records = sf_client._client().query_all(q)["records"]
    except Exception:
        # A Salesforce outage must not blank the prospect map — the yellow dots
        # are the point of the page and they come from our own database.
        logger.warning("Could not load stockists from Salesforce", exc_info=True)
        return []
    if not records:
        logger.info("No stockists match a territory naming %r", name)
    return [
        {
            "name": r["Name"],
            "territory": r.get("SalesTerritory__c"),
            "latitude": r["ShippingLatitude"],
            "longitude": r["ShippingLongitude"],
        }
        for r in records
    ]


@router.get("/prospects")
def list_prospects(rep_name: str = RepRequired, db: Session = Depends(get_db)) -> dict:
    rep_email = sheets_client.rep_email_for_writer(rep_name)
    if not rep_email:
        # Fail closed, exactly as /orders does: without an address there is no
        # way to tell this rep's territory from anyone else's.
        logger.warning("No sheet email for signed-in rep %s — showing no prospects", rep_name)
        return {
            "rep": rep_name,
            "prospects": [],
            # Stockists still load: the map is worth showing even when this
            # rep has no prospects matched to them.
            "accounts": _stockists(rep_name),
            "counts": {"total": 0, "noConflict": 0, "marked": 0},
            "message": (
                "Your name isn't in the rep contact sheet yet, so no territory "
                "can be matched to you. Ask the office to add it."
            ),
        }

    # Which territories are this rep's, decided by the same sheet that routes
    # their order email — so the dashboard and the inbox cannot disagree.
    #
    # Enumerated from SALESFORCE, not from distinct values in the prospects
    # table. A rep's territory is a property of the rep; deriving it from the
    # table meant an empty table produced an empty territory set, and the
    # stockist layer then vanished because it had nothing to look up. The
    # grey dots must not depend on the yellow ones existing.
    try:
        all_territories = sf_client.list_territories()
    except Exception:
        logger.warning("Could not list territories from Salesforce", exc_info=True)
        all_territories = []
    mine = {
        t
        for t in all_territories
        if (sheets_client.rep_email_for_territory(t) or "").casefold() == rep_email.casefold()
    }

    rows = (
        db.execute(
            select(Prospect)
            .where(Prospect.territory.in_(mine), Prospect.status == "prospect")
            .order_by(Prospect.store_name)
        )
        .scalars()
        .all()
        if mine
        else []
    )

    marked_ids = {
        m.prospect_id
        for m in db.execute(
            select(ProspectMark).where(ProspectMark.rep_name == normalize_name(rep_name))
        ).scalars()
    }

    return {
        "rep": rep_name,
        "prospects": [_prospect_row(p, p.id in marked_ids) for p in rows],
        "accounts": _stockists(rep_name),
        "counts": {
            "total": len(rows),
            "noConflict": sum(1 for p in rows if not p.potential_conflict),
            "marked": sum(1 for p in rows if p.id in marked_ids),
        },
        # An empty list has to say WHY, because three unrelated situations
        # render as the same blank page: no sheet email (handled above), no
        # territory owned, and a sweep that has simply never covered this rep's
        # states. The last one is not hypothetical — the first sweep loaded was
        # CA/HI, so every other rep opened this tab to "Showing 0 of 0
        # prospects" with nothing to say whether that was an answer or a fault.
        "message": _no_prospects_message(mine) if not rows else None,
    }


def _no_prospects_message(territories: set[str]) -> str:
    """Why this rep's prospect list is empty, in words a rep can act on.

    Names the territories rather than saying "your territories": a rep who owns
    two and expected shops in one needs to see which set was actually searched,
    and a rep who owns none is looking at a different problem entirely.
    """
    if not territories:
        return (
            "No sales territory is assigned to you in Salesforce, so there is "
            "nothing to match prospects against. Ask the office to check it."
        )
    named = ", ".join(sorted(territories))
    return (
        f"No prospects have been swept for your territory yet ({named}). "
        "This is not a fault — the search simply has not been run for your "
        "states. Ask the office to sweep them."
    )


class MarkRequest(BaseModel):
    marked: bool


@router.post("/prospects/{osm_id:path}/mark")
def mark_prospect(
    osm_id: str,
    payload: MarkRequest,
    rep_name: str = RepRequired,
    db: Session = Depends(get_db),
) -> dict:
    """Star or un-star a prospect for the signed-in rep.

    Keyed on osm_id because that is what the page holds, and `:path` because an
    osm_id looks like "node/12345" — a bare {osm_id} would stop at the slash.

    Un-starring DELETES the row rather than flipping a flag: the shortlist is
    "these ones", and an absent row is the cleanest way to say no.
    """
    p = db.execute(select(Prospect).where(Prospect.osm_id == osm_id)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Unknown prospect")

    key = normalize_name(rep_name)
    existing = db.execute(
        select(ProspectMark).where(
            ProspectMark.prospect_id == p.id, ProspectMark.rep_name == key
        )
    ).scalar_one_or_none()

    if payload.marked and existing is None:
        db.add(ProspectMark(prospect_id=p.id, rep_name=key))
    elif not payload.marked and existing is not None:
        db.delete(existing)
    db.commit()
    return {"id": osm_id, "marked": payload.marked}
