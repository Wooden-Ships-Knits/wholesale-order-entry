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
from datetime import datetime, timezone
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

# ------------------------------------------------------------------ bounces
# A bounce is NOT a reply: it comes from the mail system, not the buyer, and
# carries none of our correlation tokens. It is recognised by shape instead —
# RFC 3464 delivery-status reports — with a sender check as a fallback for the
# providers that send a plain-text failure notice.
_DSN_SENDERS = ("mailer-daemon", "postmaster", "mail-delivery")
# "Final-Recipient: rfc822; molly@monkeesofhighpoint.com"
_FINAL_RECIPIENT_RE = re.compile(
    r"^(?:Final|Original)-Recipient:\s*[^;]*;\s*(.+)$", re.I | re.M
)
# "Status: 5.1.1" — 5.x.x is permanent (the address is wrong), 4.x.x is a
# temporary defer that the sending server will retry on its own.
_DSN_STATUS_RE = re.compile(r"^Status:\s*([245])\.(\d+)\.(\d+)", re.I | re.M)
_DIAGNOSTIC_RE = re.compile(r"^Diagnostic-Code:\s*(.+)$", re.I | re.M)
# The short id we put at the end of every order subject, recovered from the
# bounced original that the DSN quotes back.
_SHORT_ID_RE = re.compile(r"\b([0-9a-f]{8})\b")


@dataclass
class ParsedBounce:
    """A permanent delivery failure, and who it was for."""

    recipient: str
    reason: str
    # Short ids found in the quoted original subject; used to disambiguate when
    # the same address is on more than one outstanding order.
    short_ids: list[str] = field(default_factory=list)
    message_id: str | None = None
    received_at: datetime | None = None


def _is_bounce(msg: Message) -> bool:
    ctype = (msg.get_content_type() or "").lower()
    if ctype == "multipart/report":
        return "delivery-status" in str(msg.get_param("report-type") or "").lower()
    sender = parseaddr(str(msg.get("From") or ""))[1].lower()
    return any(s in sender for s in _DSN_SENDERS)


def extract_bounce(raw: bytes) -> ParsedBounce | None:
    """A ParsedBounce for a PERMANENT failure, else None.

    Temporary failures (4.x.x) are ignored on purpose: the sending server keeps
    retrying, and flagging the order would tell the team an address is wrong
    when the message is still on its way.
    """
    try:
        msg = message_from_bytes(raw, policy=policy.default)
    except Exception:
        logger.warning("Could not parse an inbound message while scanning for bounces")
        return None
    if not _is_bounce(msg):
        return None

    # Walk the whole message: the delivery-status part holds the machine-
    # readable fields, and the rfc822 part quotes what we originally sent.
    status_text, original_subject = "", ""
    for part in msg.walk():
        ctype = (part.get_content_type() or "").lower()
        if ctype == "message/delivery-status":
            status_text += str(part)
        elif ctype in ("message/rfc822", "text/rfc822-headers"):
            for sub in part.walk() if part.is_multipart() else [part]:
                original_subject += " " + str(sub.get("Subject") or "")

    permanent = _DSN_STATUS_RE.search(status_text)
    if permanent and permanent.group(1) != "5":
        return None  # 4.x.x — still being retried, not a wrong address
    if not permanent and not _is_bounce(msg):
        return None

    recipients = [r.strip().strip("<>") for r in _FINAL_RECIPIENT_RE.findall(status_text)]
    if not recipients:
        return None

    diag = _DIAGNOSTIC_RE.search(status_text)
    reason = (diag.group(1).strip() if diag else "").strip()
    if not reason:
        reason = "Address not found" if permanent else "Delivery failed"

    return ParsedBounce(
        recipient=recipients[0].lower(),
        reason=reason[:500],
        short_ids=_SHORT_ID_RE.findall(original_subject.lower()),
        message_id=str(msg.get("Message-ID") or "") or None,
        received_at=_received_at(msg),
    )


def parse_bounces(raws: Iterable[bytes]) -> list[ParsedBounce]:
    return [b for b in (extract_bounce(r) for r in raws) if b is not None]


def apply_bounce(db, bounce: ParsedBounce) -> Order | None:
    """Stamp the order whose signature request this bounce is for, or None.

    Matched on the failed recipient against orders still waiting on a
    signature. When one address has several outstanding orders, the short id
    quoted back in the DSN picks the right one; without it we would flag an
    order whose email may have been fine.
    """
    candidates = list(
        db.execute(
            select(Order).where(
                Order.signature_signed_at.is_(None),
                Order.signature_requested_at.is_not(None),
                Order.signature_email.isnot(None),
            )
        ).scalars()
    )
    matches = [
        o for o in candidates if (o.signature_email or "").strip().lower() == bounce.recipient
    ]
    if len(matches) > 1 and bounce.short_ids:
        narrowed = [o for o in matches if str(o.id)[:8] in bounce.short_ids]
        if narrowed:
            matches = narrowed
    if not matches:
        logger.info(
            "Bounce for %s matched no order awaiting a signature", bounce.recipient
        )
        return None
    # Newest first: a resent request is the one that just bounced.
    order = sorted(matches, key=lambda o: o.signature_requested_at, reverse=True)[0]
    order.signature_bounced_at = bounce.received_at or datetime.now(timezone.utc)
    order.signature_bounce_reason = bounce.reason
    logger.warning(
        "Signature request for order %s bounced (%s): %s",
        str(order.id)[:8], bounce.recipient, bounce.reason,
    )
    return order


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
        # Fetched once and scanned twice: fetching marks messages \Seen, so a
        # second pass over the mailbox would find nothing.
        raws = fetch_unseen_raw(conn)
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    replies = parse_replies(raws)

    # Bounces are handled before replies and independently of them: a delivery
    # failure carries none of our correlation tokens, so parse_replies drops it.
    bounced = 0
    for b in parse_bounces(raws):
        if apply_bounce(db, b) is not None:
            bounced += 1
    if bounced:
        db.commit()

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
