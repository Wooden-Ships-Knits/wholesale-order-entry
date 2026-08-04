"""POST /api/send-email — admin-only. Sends a drafted email (To/Cc/Subject/Body)
through the configured SMTP account.

Backs the "Send Mail" button in the admin email-draft modal (conflict-inquiry
and tax-certificate drafts). Text only — no attachments. The admin edits the
draft, then this endpoint hands it to Gmail via app.email.mailer.

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
    sent = mailer.send_email(to, payload.subject, payload.body, cc=cc, reply_to=reply_to)
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
                db.commit()
        except Exception:
            logger.exception("Sent email but could not stamp order %s", payload.orderId)
            db.rollback()

    logger.info("Admin sent a drafted email to %s (cc %s)", to, cc)
    return {"sent": True}
