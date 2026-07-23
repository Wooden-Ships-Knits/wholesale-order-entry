"""SMTP transport for outbound app email (order copies + admin notice).

Pure transport — no order/business logic. Uses stdlib smtplib so it fits the
synchronous request / BackgroundTasks flow without an async dependency. Silently
no-ops (logs a warning) when SMTP isn't configured, so the app runs without mail
credentials and an order is never blocked by mail.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    cc: str | None = None,
) -> bool:
    """Send a plain-text email with optional attachments and CC.

    attachments: list of (filename, data, mime_subtype), e.g.
    ("WS-order.pdf", b"%PDF...", "pdf"). cc: comma-separated address(es), added
    as a Cc header so smtplib also delivers to them. Returns True on send, False
    if SMTP is not configured or any error occurs (both logged; never raises).
    """
    if not settings.mail_configured:
        logger.warning("Email not sent to %s: SMTP is not configured", to)
        return False

    msg = EmailMessage()
    msg["From"] = settings.mail_sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg.set_content(body)
    for filename, data, subtype in attachments or []:
        msg.add_attachment(data, maintype="application", subtype=subtype, filename=filename)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
    return True
