"""POST /api/send-email — admin-only. Sends a drafted email (To/Cc/Subject/Body)
through the configured SMTP account.

Backs the "Send Mail" button in the admin email-draft modal (conflict-inquiry
and tax-certificate drafts). Text only — no attachments. The admin edits the
draft, then this endpoint hands it to Gmail via app.email.mailer.
"""
import logging

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from app.admin.security import AdminRequired
from app.config import settings
from app.email import mailer

logger = logging.getLogger(__name__)

router = APIRouter()


class SendEmailRequest(BaseModel):
    """To and CC are both required (mirrored on the client); subject/body may
    be empty. CC is comma-separated to match the modal's single input."""

    to: str = Field(min_length=1, max_length=254)
    cc: str = Field(min_length=1, max_length=1000)
    subject: str = Field("", max_length=500)
    body: str = Field("", max_length=20000)


@router.post("/send-email", dependencies=[AdminRequired])
def send_drafted_email(payload: SendEmailRequest) -> dict:
    if not settings.mail_configured:
        raise HTTPException(
            status_code=503, detail="Email is not configured on the server."
        )

    to = payload.to.strip()
    cc = payload.cc.strip()
    sent = mailer.send_email(to, payload.subject, payload.body, cc=cc)
    if not sent:
        raise HTTPException(status_code=502, detail="The email could not be sent.")

    logger.info("Admin sent a drafted email to %s (cc %s)", to, cc)
    return {"sent": True}
