"""POST /api/send-email — admin-only. Sends a drafted email (To/Cc/Subject/Body)
through the configured SMTP account.

Backs the "Send Mail" button in the admin email-draft modal (conflict-inquiry,
tax-certificate and signature-request drafts). The admin edits the draft, then
this endpoint hands it to Gmail via app.email.mailer.

Text only, with one exception: kind="signature" attaches the order's PDF, to
match the automatic send at submit
(routers/orders.py::_send_signature_request) — a resent request must not be a
lesser email than the one it replaces. The PDF is re-rendered from the order
row and card-masked — see app/pdf/context.py.

When the caller passes an orderId + kind ("conflict" | "tax_cert"), a successful
send is stamped on that order so the button shows a persistent "Sent ✓" that
survives a page reload. The conflict-check tab (no order behind it) omits both
and just sends.
"""
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin.security import AdminRequired
from app.config import settings
from app.db.models import Order
from app.db.session import get_db
from app.email import mailer, reply_address
from app.pdf import context as pdf_context
from app.pdf import render as pdf_render

logger = logging.getLogger(__name__)

router = APIRouter()

# kind -> the order column stamped on a successful send.
_SENT_COLUMN = {
    "conflict": "conflict_email_sent_at",
    "tax_cert": "tax_cert_email_sent_at",
    "signature": "signature_requested_at",
}

# Kinds whose reply should route back correlated to the order. "signature" is
# absent on purpose: the buyer answers by clicking the link, and a plus-address
# Reply-To would send their questions into the automated inbound parser instead
# of to a person.
_REPLY_TAGGED = ("conflict", "tax_cert")


class SendEmailRequest(BaseModel):
    """To is required (mirrored on the client); CC is optional — conflict emails
    have no CC (they go to the rep only), so an empty cc must be accepted.
    subject/body may be empty. CC is comma-separated to match the modal's single
    input. orderId + kind are optional — when both are given, a successful send
    is recorded on that order."""

    to: str = Field(min_length=1, max_length=254)
    cc: str = Field("", max_length=1000)
    subject: str = Field("", max_length=500)
    body: str = Field("", max_length=20000)
    orderId: str | None = Field(None, max_length=36)
    kind: Literal["conflict", "tax_cert", "signature"] | None = None


def _order_pdf_attachment(db: Session, order_id: str) -> list[tuple[str, bytes, str]] | None:
    """The order's card-masked PDF, re-rendered from the row. None on failure.

    Best-effort on purpose: a signature request without its attachment is worth
    far more to the buyer than no email at all, since the link is what actually
    matters. The miss is logged.
    """
    try:
        order = db.get(Order, order_id)
        if order is None:
            return None
        context = pdf_context.build(order)
        context["card"] = pdf_context.masked_card(order)
        return [(
            pdf_render.order_pdf_filename(
                order.season_code, order.buyer_name or "", order.created_at, order.id
            ),
            pdf_render.render_order_pdf(context),
            "pdf",
        )]
    except Exception:
        logger.exception("Could not attach the order PDF for %s — sending without it", order_id)
        return None


@router.post("/send-email", dependencies=[AdminRequired])
def send_drafted_email(payload: SendEmailRequest, db: Session = Depends(get_db)) -> dict:
    if not settings.mail_configured:
        raise HTTPException(
            status_code=503, detail="Email is not configured on the server."
        )

    to = payload.to.strip()
    cc = payload.cc.strip()
    # Tag with a plus-addressed Reply-To so the reply routes back correlated to
    # this order (see app/email/reply_address.py): a rep's conflict decision, or
    # a customer's tax-cert reply carrying the certificate attachment.
    reply_to = None
    if payload.orderId and payload.kind in _REPLY_TAGGED:
        reply_to = reply_address.build_reply_to(
            payload.orderId, payload.kind, settings.mail_sender
        )
    attachments = None
    if payload.orderId and payload.kind == "signature":
        attachments = _order_pdf_attachment(db, payload.orderId)

    # The signature draft ships with **bold** / __underline__ markers in it, and
    # the admin can add more while editing. Render them rather than mailing the
    # raw asterisks out to a customer; a body with no markers is unaffected.
    sent = mailer.send_email(
        to, payload.subject, payload.body, attachments, cc=cc, reply_to=reply_to,
        html=mailer.html_from_text(payload.body),
    )
    if not sent:
        raise HTTPException(status_code=502, detail="The email could not be sent.")

    # Record the send on the order so the admin button stays "Sent ✓" after a
    # reload. Best-effort: the email already went out, so a stamping failure
    # must not turn a successful send into an error.
    if payload.orderId and payload.kind:
        try:
            order = db.get(Order, payload.orderId)
            if order is not None:
                setattr(order, _SENT_COLUMN[payload.kind], datetime.now(timezone.utc))
                # Remember where a signing link went, so it can be re-sent
                # without the admin retyping the address.
                if payload.kind == "signature":
                    order.signature_email = to
                    # Sent again, possibly to a corrected address — drop any
                    # recorded bounce so the row and the chasers reset.
                    order.signature_bounced_at = None
                    order.signature_bounce_reason = None
                db.commit()
        except Exception:
            logger.exception("Sent email but could not stamp order %s", payload.orderId)
            db.rollback()

    logger.info("Admin sent a drafted email to %s (cc %s)", to, cc)
    return {"sent": True}
