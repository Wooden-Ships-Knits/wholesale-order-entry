"""Chase unsigned orders automatically.

An order whose buyer has a live signing link is re-sent the SAME email at the
ages in settings.signature_reminder_hours, counted from when the first request
left. Nothing else changes: same token, same link, same expiry. A
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
from app.email import mailer, order_email, signature_template
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


def skip_elapsed_stages(order: Order, now: datetime | None = None) -> None:
    """Move both cursors past every threshold this order has already outlived.

    Called on a MANUAL resend. The anchor deliberately does not move (chasing is
    spaced from the first request, not from whoever last intervened), which
    leaves every threshold between the last send and now sitting overdue. The
    sweep fires ONE rung per order per tick, so a backlog does not collapse into
    a single email -- it becomes one an hour until the cursor catches up. An
    order that spent three weeks on an expired link would mail the buyer four
    times in four hours, immediately after a person had just written to them.

    Skipping is the right answer rather than sending: the buyer has this moment
    been emailed by hand, so a reminder that they have not replied is both false
    and annoying. Reminders are a schedule, not a debt -- a missed one is missed,
    not owed.

    Never rewinds: max() against the stored value, so a cursor already ahead of
    the elapsed count (a schedule that was shortened underneath in-flight orders,
    which is exactly what the 2026-08-21 rewrite did) keeps its place.
    """
    if order.signature_requested_at is None:
        return
    now = now or datetime.now(timezone.utc)
    age = now - order.signature_requested_at

    elapsed = sum(1 for h in settings.signature_reminder_hours if timedelta(hours=h) <= age)
    order.signature_reminders_sent = max(order.signature_reminders_sent or 0, elapsed)

    elapsed_rep = sum(1 for h in settings.rep_followup_hours if timedelta(hours=h) <= age)
    order.rep_followups_sent = max(order.rep_followups_sent or 0, elapsed_rep)


def _candidates(db: Session, now: datetime) -> list[Order]:
    """Orders with a live link that has already been emailed once.

    signature_requested_at NOT NULL is the anchor: an order whose first request
    never left has nothing to chase from, and re-sending it is the admin's job.
    A signed order has no token, and a cancelled link has none either, so the
    token test covers both without naming them.

    Expiry is checked here as well as by the token: expiring does NOT clear
    signature_token (only signing and Cancel link do), so without this an
    order past its expiry would keep matching and we would mail the buyer a
    link that 410s. A reminder that can't be acted on is worse than silence.
    """
    return list(
        db.scalars(
            select(Order).where(
                Order.signature_token.is_not(None),
                Order.signature_signed_at.is_(None),
                Order.signature_requested_at.is_not(None),
                Order.signature_token_expires_at > now,
                Order.status == "submitted",
                # The address bounced — five more chasers would go to the same
                # dead mailbox. Cleared when the request is sent again, so a
                # corrected address resumes the schedule.
                Order.signature_bounced_at.is_(None),
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
        short_id=str(order.id)[:8],
    )
    # No CC — see routers/orders.py::_send_signature_request. The link must not
    # reach the rep's inbox, and a chaser is the same link five more times.

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
        draft["to"], draft["subject"], draft["body"], attachments,
        html=mailer.html_from_text(draft["body"]),
    )


def _order_pdf(order: Order) -> tuple[str, bytes] | None:
    """(filename, bytes) of the order's card-masked PDF, or None if it fails."""
    try:
        context = pdf_context.build(order)
        context["card"] = pdf_context.masked_card(order)
        return (
            pdf_render.order_pdf_filename(
                order.season_code, order.buyer_name or "", order.created_at, order.id
            ),
            pdf_render.render_order_pdf(context),
        )
    except Exception:
        logger.exception("Order %s: PDF render failed", str(order.id)[:8])
        return None


def send_due_rep_followups(db: Session) -> int:
    """Nudge the rep at each age in settings.rep_followup_hours (days 6, 16, 26).

    Deliberately NOT filtered on signature_bounced_at, unlike the buyer's
    chasers: a bounced address is the case where the rep most needs telling,
    because nothing will reach the buyer by email at all until someone corrects
    it. The chasers stop; these still go.

    STAGE 1 USES DIFFERENT WORDING FROM 2 AND 3. Day 6 says "email is not
    working, please call"; the later ones say "we asked you ten days ago".
    Repeating the day-6 text would read as an automated echo, not an escalation.

    rep_followups_sent is written and committed BEFORE the send, so a crash
    costs one nudge rather than repeating it on every tick — the same trade the
    buyer's chasers make.
    """
    schedule = settings.rep_followup_hours
    if not schedule:
        return 0

    now = datetime.now(timezone.utc)
    # Only the FIRST unsent stage can be due, so the cutoff is the earliest
    # threshold any candidate could have crossed.
    due = list(
        db.scalars(
            select(Order).where(
                Order.signature_token.is_not(None),
                Order.signature_signed_at.is_(None),
                Order.signature_requested_at.is_not(None),
                Order.signature_token_expires_at > now,
                Order.status == "submitted",
                Order.rep_followups_sent < len(schedule),
                Order.signature_requested_at <= now - timedelta(hours=min(schedule)),
            )
        )
    )

    sent = 0
    for order in due:
        stage = order.rep_followups_sent or 0
        if stage >= len(schedule):
            continue
        age = now - order.signature_requested_at
        if age < timedelta(hours=schedule[stage]):
            continue  # this order has not reached its NEXT stage yet

        short_id = str(order.id)[:8]
        rep_to = sheets_client.rep_email_for_order(
            order.order_written_by, order.sales_territory
        )
        if not rep_to:
            logger.info(
                "Order %s is still unsigned but no rep email resolves for writer "
                "%r / territory %r — no follow-up sent",
                short_id, order.order_written_by, order.sales_territory,
            )
            # Counted anyway: without a rep address there is nobody to tell, and
            # leaving the cursor put would re-check this order every hour.
            order.rep_followups_sent = stage + 1
            order.rep_followup_sent_at = now
            db.commit()
            continue

        order.rep_followups_sent = stage + 1
        order.rep_followup_sent_at = now
        db.commit()

        rendered = _order_pdf(order)
        if rendered is None:
            continue
        filename, pdf_bytes = rendered
        ctx = {
            "short_id": short_id,
            "season_code": order.season_code,
            "season_label": mapping.season_label(order.season_code),
            "account_name": order.account_name,
            "buyer_name": order.buyer_name,
            "total_qty": order.total_qty,
            "total_amount": order.total_amount,
        }
        send = order_email.send_rep_followup if stage == 0 else order_email.send_rep_chase
        try:
            if send(rep_to, ctx, pdf_bytes, filename):
                sent += 1
                logger.info(
                    "Rep follow-up %d/%d sent for unsigned order %s",
                    stage + 1, len(schedule), short_id,
                )
            else:
                logger.error("Rep follow-up for order %s could not be sent", short_id)
        except Exception:
            logger.exception("Rep follow-up for order %s raised", short_id)
    return sent


def send_due_reminders(db: Session) -> int:
    """Send every reminder that has come due. Returns how many left."""
    if not settings.signature_reminder_hours:
        return 0

    now = datetime.now(timezone.utc)
    sent = 0
    for order in _candidates(db, now):
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
