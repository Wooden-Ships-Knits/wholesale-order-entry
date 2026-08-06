"""SMTP transport for outbound app email (order copies + admin notice).

Pure transport — no order/business logic. Uses stdlib smtplib so it fits the
synchronous request / BackgroundTasks flow without an async dependency. Silently
no-ops (logs a warning) when SMTP isn't configured, so the app runs without mail
credentials and an order is never blocked by mail.

Emphasis: mark words up inside the ordinary plain-text body — **bold** and
__underline__ — and pass html=html_from_text(body) when sending. There is
deliberately no second HTML template to maintain: one body is the source of
truth, the markers are stripped from the text part, and a body with no markers
sends as plain text exactly as before.
"""
import html as html_escape
import logging
import re
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

# **bold** and __underline__. Non-greedy and newline-free on both sides, so an
# unpaired marker cannot swallow the rest of the email; the \s guards stop
# "a ** b ** c" from turning stray asterisks into markup.
_BOLD_RE = re.compile(r"\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*")
_UNDER_RE = re.compile(r"__(?!\s)([^_\n]+?)(?<!\s)__")
_URL_RE = re.compile(r"https?://[^\s<>\"]+")


def _outside_urls(body: str, fn) -> str:
    """Apply fn to everything except the URLs, which pass through untouched.

    Signing tokens are secrets.token_urlsafe, whose alphabet includes "_", so a
    link can contain a run of two underscores by chance. Left to the underline
    rule that becomes <u> in the HTML and a silently shortened token in the
    plain text — a signing link that 404s for the buyer. URLs are therefore
    never marked up.
    """
    out, last = [], 0
    for m in _URL_RE.finditer(body):
        out.append(fn(body[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(fn(body[last:]))
    return "".join(out)


def _marked(body: str) -> bool:
    hits = []
    _outside_urls(body, lambda s: hits.append(_BOLD_RE.search(s) or _UNDER_RE.search(s)) or s)
    return any(hits)


def strip_marks(body: str) -> str:
    """The plain-text part: **word** -> word, __word__ -> word."""
    return _outside_urls(body, lambda s: _UNDER_RE.sub(r"\1", _BOLD_RE.sub(r"\1", s)))


def html_from_text(body: str) -> str | None:
    """An HTML alternative for a body that uses **bold** / __underline__, else None.

    None means "nothing to style" — send_email then sends plain text only, so
    every existing template keeps its current, single-part behaviour until
    someone actually marks a word up.

    Escapes first, then marks up, so the order data inside the body (a store
    called "Smith & Sons") can never inject markup.
    """
    if not _marked(body):
        return None

    def markup(segment: str) -> str:
        segment = _BOLD_RE.sub(r"<strong>\1</strong>", segment)
        return _UNDER_RE.sub(r"<u>\1</u>", segment)

    out = _outside_urls(html_escape.escape(body), markup)
    # The signing link is the point of one of these emails — make it clickable
    # rather than a bare string the buyer has to copy out.
    out = _URL_RE.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', out)
    out = out.replace("\n", "<br>\n")
    # Plain sans-serif, and only faces every mail client already has: webfonts
    # are stripped by most of them, and a serif here would not match the
    # client's own default face for the plain-text part of the same message.
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif; font-size:14px; '
        f'line-height:1.5; color:#1d1d1b;">\n{out}\n</div>'
    )


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    cc: str | None = None,
    reply_to: str | None = None,
    html: str | None = None,
) -> bool:
    """Send an email with optional attachments and CC.

    attachments: list of (filename, data, mime_subtype), e.g.
    ("WS-order.pdf", b"%PDF...", "pdf"). cc: comma-separated address(es), added
    as a Cc header so smtplib also delivers to them. reply_to: a Reply-To header
    (e.g. a plus-addressed correlation address) so replies route where we can
    track them. html: an alternative HTML part — pass html_from_text(body) to
    render **bold** / __underline__ markers; omit (or None) for plain text.
    Returns True on send, False if SMTP is not configured or any error occurs
    (both logged; never raises).
    """
    if not settings.mail_configured:
        logger.warning("Email not sent to %s: SMTP is not configured", to)
        return False

    # Dev mode: every message goes to one inbox instead of the real recipients.
    # Done HERE rather than at the five call sites because this is the only
    # place an address can turn into a delivery — a caller cannot bypass it, and
    # no future call site has to remember the rule.
    redirect = settings.mail_redirect_to
    if redirect:
        original_to, original_cc = to, cc
        to, cc = redirect, None
        subject = f"[DEV → {original_to}] {subject}"
        banner = (
            "*** DEV MODE — this message was NOT delivered to its real recipients ***\n"
            f"Would have gone to: {original_to}\n"
            + (f"Cc: {original_cc}\n" if original_cc else "")
            + ("-" * 60)
            + "\n\n"
        )
        body = banner + body
        if html:
            html = (
                '<div style="background:#fbeeec;border:1px solid #b03a2e;color:#7a281f;'
                'padding:10px 12px;margin-bottom:16px;font-family:sans-serif;font-size:13px">'
                "<strong>DEV MODE — not delivered to the real recipients.</strong><br>"
                f"Would have gone to: {original_to}"
                + (f"<br>Cc: {original_cc}" if original_cc else "")
                + "</div>"
                + html
            )
        logger.info("DEV redirect: %s (cc %s) -> %s", original_to, original_cc or "-", redirect)

    msg = EmailMessage()
    msg["From"] = settings.mail_sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    # The text part always ships, HTML or not: it is what a plain-text client
    # renders, and it must not show the raw ** markers.
    msg.set_content(strip_marks(body))
    if html:
        # Order matters — the alternative has to exist before the attachments,
        # or EmailMessage nests the PDF inside multipart/alternative and some
        # clients treat it as a body variant rather than a file.
        msg.add_alternative(html, subtype="html")
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
