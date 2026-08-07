"""Chase unsigned orders automatically.

An order whose buyer has a live signing link is re-sent the SAME email at the
ages in settings.signature_reminder_hours (48h and 96h after the first request
left). Nothing else changes: same token, same link, same expiry date. A
reminder is a nudge, not a new request — minting a fresh token would leave the
buyer's earlier email holding a link that had silently stopped working.

Ordering matters for correctness: the counter is incremented and COMMITTED
before the mail is attempted, so a crash mid-send costs one reminder rather
than re-sending on every tick forever. The first request works the other way
round (stamp only after SMTP succeeds) because there the stamp means "the
buyer has been told at all" and a false positive would strand the order.

Runs from a background loop in app/main.py rather than a scheduler container —
same reasoning as the card-retention sweep, which piggybacks on the admin page
load. This one can't do that: chasing has to happen whether or not anyone
opens /admin.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Order
from app.email import mailer, signature_template
from app.pdf import context as pdf_context
from app.pdf import render as pdf_render
from app.salesforce import mapping
from app.sheets import client as sheets_client

logger = logging.getLogger(__name__)


def _due(order: Order, now: datetime) -> bool:
    """Has this order reached the next threshold in the schedule?"""
    schedule = settings.signature_reminder_hours
    sent = order.signature_reminders_sent or 0
    if sent >= len(schedule):
        return False  # every reminder in the schedule has gone out
    return now - order.signature_requested_at >= timedelta(hours=schedule[sent])


def _candidates(db: Session) -> list[Order]:
    """Orders with a live link that has already been emailed once.

    signature_requested_at NOT NULL is the anchor: an order whose first request
    never left has nothing to chase from, and re-sending it is the admin's job.
    A signed order has no token, and a cancelled link has none either, so the
    token test covers both without naming them.
    """
    return list(
        db.scalars(
            select(Order).where(
                Order.signature_token.is_not(None),
                Order.signature_signed_at.is_(None),
                Order.signature_requested_at.is_not(None),
                Order.status == "submitted",
            )
        )
    )


def _send(order: Order) -> bool:
    """Re-send the signature request for one order. True if the mail left."""
    from app.routers.sign import sign_url  # local: routers import services

    draft = signature_template.build(
        to_email=order.signature_email or order.ship_email,
        sign_url=sign_url(order.signature_token),
        account_name=order.account_name,
        season_label=mapping.season_label(order.season_code),
        total_qty=order.total_qty,
        total_amount=order.total_amount,
        expires_on=order.signature_token_expires_at,
        short_id=str(order.id)[:8],
    )
    cc = sheets_client.rep_email_for_order(order.order_written_by, order.sales_territory)

    # Re-rendered from the order row rather than read off disk: the buyer may
    # have been sent a link before an admin corrected the store or the ship
    # window, and the chaser should carry what the order says now. Card-masked,
    # like every copy that leaves the server.
    attachments = None
    try:
        context = pdf_context.build(order)
        context["card"] = pdf_context.masked_card(order)
        attachments = [(
            pdf_render.order_pdf_filename(
                order.season_code, order.buyer_name or "", order.created_at, order.id
            ),
            pdf_render.render_order_pdf(context),
            "pdf",
        )]
    except Exception:
        logger.exception(
            "Order %s: could not render the PDF for its reminder — sending without it",
            str(order.id)[:8],
        )

    return mailer.send_email(
        draft["to"], draft["subject"], draft["body"], attachments, cc=cc,
        html=mailer.html_from_text(draft["body"]),
    )


def send_due_reminders(db: Session) -> int:
    """Send every reminder that has come due. Returns how many left."""
    if not settings.signature_reminder_hours:
        return 0

    now = datetime.now(timezone.utc)
    sent = 0
    for order in _candidates(db):
        if not _due(order, now):
            continue
        short_id = str(order.id)[:8]
        which = (order.signature_reminders_sent or 0) + 1

        # Committed BEFORE the send — see the module docstring. A failed send
        # is logged and skipped rather than retried, so a permanently bad
        # address can't hold up the whole sweep on every tick.
        order.signature_reminders_sent = which
        order.signature_reminded_at = now
        db.commit()

        try:
            ok = _send(order)
        except Exception:
            logger.exception("Reminder %d for order %s raised", which, short_id)
            continue
        if ok:
            sent += 1
            logger.info("Reminder %d sent for unsigned order %s", which, short_id)
        else:
            logger.error(
                "Reminder %d for order %s could not be sent — resend from /admin",
                which, short_id,
            )
    return sent
