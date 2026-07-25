"""Inbound reply capture.

Reads the wholesale@ mailbox over IMAP, correlates each reply to its order via
the plus-address token (see :mod:`app.email.reply_address`), and stores the
rep's message as an :class:`~app.db.models.InboundReply` for the classifier to
read later.

The email-parsing and dedupe logic is pure and unit-tested. The IMAP/DB plumbing
(:func:`fetch_unseen_raw`, :func:`run_poll`) is thin and, like the mailer,
no-ops when IMAP isn't configured so the app runs without inbound credentials.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_bytes, policy
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime, parseaddr
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from app.config import settings
from app.db.models import InboundReply, Order
from app.email import reply_address
from app.pdf import render as pdf_render

logger = logging.getLogger(__name__)

# Headers that may carry the plus-addressed recipient we tagged the outbound
# email with. The rep's reply usually has it on To; some providers only keep it
# on Delivered-To / X-Original-To.
_RECIPIENT_HEADERS = ("Delivered-To", "X-Original-To", "To", "Cc")
_SNIPPET_MAX = 2000

# Fallback correlation: the kind-tagged token we stamp into an email subject
# ("… [#<kind>-<order-uuid>]"), which survives a reply to the bare wholesale@
# address. Same "<kind>-<id>" shape as the plus-address token.
_SUBJECT_TOKEN_RE = re.compile(
    r"\[#([a-z_]+-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]"
)

# A tax-cert reply's certificate is one of these attached to the message.
_CERT_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}


@dataclass
class ParsedReply:
    order_id: str
    kind: str
    from_address: str | None
    subject: str | None
    snippet: str | None
    message_id: str | None
    received_at: datetime | None
    # (filename, bytes, content_type, disposition) for each attached file.
    attachments: list[tuple[str, bytes, str, str | None]] = field(default_factory=list)


def _correlate(msg: Message) -> tuple[str, str] | None:
    """(order_id, kind) for this reply, or None.

    Primary: the plus-address token in a recipient header. Fallback: the order
    token in the subject line, which survives a reply to the bare wholesale@
    address (no plus-token). The plus-token is authoritative when both exist."""
    values = [v for h in _RECIPIENT_HEADERS for v in msg.get_all(h, [])]
    for _, addr in getaddresses(values):
        hit = reply_address.parse_reply_to(addr)
        if hit:
            return hit
    subject = msg.get("Subject")
    if subject:
        m = _SUBJECT_TOKEN_RE.search(str(subject))
        if m:
            return reply_address.parse_token(m.group(1))
    return None


def _plain_body(msg: Message) -> str:
    """The first text/plain part's text (skipping attachments), truncated."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    text = part.get_content()
                except Exception:  # undecodable part — skip it
                    continue
                return text.strip()[:_SNIPPET_MAX]
        return ""
    try:
        return (msg.get_content() or "").strip()[:_SNIPPET_MAX]
    except Exception:
        return ""


def _attachments(msg: Message) -> list[tuple[str, bytes, str, str | None]]:
    """Every named part's (filename, bytes, content_type, disposition)."""
    out: list[tuple[str, bytes, str, str | None]] = []
    if not msg.is_multipart():
        return out
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        try:
            data = part.get_payload(decode=True)
        except Exception:
            continue
        if data:
            out.append((filename, data, part.get_content_type(), part.get_content_disposition()))
    return out


def _received_at(msg: Message) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def extract_reply(raw: bytes) -> ParsedReply | None:
    """Parse a raw RFC822 message into a ParsedReply, or None if it carries no
    correlation token (not a reply to one of our tagged emails)."""
    # policy.default → EmailMessage with get_content() and header decoding.
    msg = message_from_bytes(raw, policy=policy.default)
    hit = _correlate(msg)
    if hit is None:
        return None
    order_id, kind = hit
    subject = msg.get("Subject")
    message_id = msg.get("Message-ID")
    return ParsedReply(
        order_id=order_id,
        kind=kind,
        from_address=parseaddr(msg.get("From", ""))[1] or None,
        subject=str(subject) if subject is not None else None,
        snippet=_plain_body(msg) or None,
        message_id=str(message_id) if message_id is not None else None,
        received_at=_received_at(msg),
        attachments=_attachments(msg),
    )


def save_tax_cert(order: Order, reply: ParsedReply) -> bool:
    """Save the resale certificate a customer attached to their tax-cert reply,
    into the same secure store the form upload uses, and stamp order.cert_filename
    (which makes the admin tax-cert cell show "Open"). Returns False when the
    reply carries no usable certificate attachment.

    Prefers a PDF; otherwise the first non-inline image — so an inline signature
    logo is never mistaken for the certificate.
    """
    candidates = [
        (fn, data)
        for (fn, data, _ctype, disp) in reply.attachments
        if Path(fn).suffix.lower() in _CERT_EXTS and disp != "inline"
    ]
    if not candidates:
        return False
    filename, data = next(
        (c for c in candidates if Path(c[0]).suffix.lower() == ".pdf"), candidates[0]
    )
    cert_name = pdf_render.cert_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id, filename
    )
    pdf_render.save_output_file(data, cert_name)
    order.cert_filename = cert_name
    logger.info("Saved emailed tax cert for order %s: %s", str(order.id)[:8], cert_name)
    return True


def parse_replies(raws: Iterable[bytes]) -> list[ParsedReply]:
    """extract_reply over many raw messages, dropping the untokened ones."""
    parsed = (extract_reply(raw) for raw in raws)
    return [r for r in parsed if r is not None]


def select_new(
    replies: Iterable[ParsedReply], existing_message_ids: set[str]
) -> list[ParsedReply]:
    """Drop replies whose Message-ID we've already stored, so a re-fetch of the
    same message can't double-record it."""
    return [r for r in replies if r.message_id not in existing_message_ids]


def fetch_unseen_raw(conn) -> list[bytes]:
    """Raw bytes of every UNSEEN message. Fetching RFC822 marks them \\Seen, so
    the next poll skips them. `conn` is an imaplib IMAP4 connection (or a stand-
    in with the same search/fetch shape)."""
    typ, data = conn.search(None, "UNSEEN")
    if typ != "OK":
        return []
    ids = (data[0] or b"").split()
    raws: list[bytes] = []
    for num in ids:
        ftyp, fdata = conn.fetch(num, "(RFC822)")
        if ftyp != "OK" or not fdata or not isinstance(fdata[0], tuple):
            continue
        raws.append(fdata[0][1])
    return raws


def run_poll(db) -> int:
    """Connect, capture new replies, and store them. Returns how many new
    InboundReply rows were created. No-op (returns 0) when IMAP isn't
    configured, mirroring the outbound mailer."""
    if not settings.imap_configured:
        logger.info("Inbound poll skipped: IMAP is not configured")
        return 0

    import imaplib

    conn = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    try:
        conn.login(settings.imap_user, settings.imap_pass)
        conn.select(settings.imap_mailbox)
        replies = parse_replies(fetch_unseen_raw(conn))
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    if not replies:
        return 0

    ids = {r.message_id for r in replies if r.message_id}
    existing = set(
        db.execute(
            select(InboundReply.message_id).where(InboundReply.message_id.in_(ids))
        ).scalars()
    )
    fresh = select_new(replies, existing)
    for r in fresh:
        db.add(
            InboundReply(
                order_id=r.order_id,
                kind=r.kind,
                from_address=r.from_address,
                subject=r.subject,
                snippet=r.snippet,
                message_id=r.message_id,
                received_at=r.received_at,
            )
        )
        # A tax-cert reply carries the certificate itself — save it onto the
        # order so the dashboard flips to "Open". (Conflict replies are handled
        # by the classifier instead.)
        if r.kind == "tax_cert":
            order = db.get(Order, r.order_id)
            if order is not None:
                save_tax_cert(order, r)
    db.commit()
    logger.info("Captured %d new inbound repl%s", len(fresh), "y" if len(fresh) == 1 else "ies")
    return len(fresh)
