"""Draft email asking the buyer to review and sign their order.

Text only: this module never sends anything. The endpoint hands the draft to
the admin UI, where a human edits it and sends it (POST /api/send-email).

Unlike the conflict email this one goes to the CUSTOMER, so it names nothing
internal — no rep, no territory, no other stockists, no rank. It carries one
link, and that link is a credential: anyone the buyer forwards it to can edit
and sign the order. The body says so plainly rather than assuming the buyer
infers it.

The same body is used for the automatic chasers (app/services/
signature_reminders.py), so nothing in it may read as first-contact-only.
"""
from datetime import date, datetime


def build(
    *,
    to_email: str | None,
    sign_url: str,
    cc_email: str | None = None,
    account_name: str | None = None,
    season_label: str | None = None,
    total_qty: int | None = None,
    total_amount=None,
    expires_on: date | datetime | None = None,
    short_id: str | None = None,
) -> dict:
    """-> {to, cc, subject, body}.

    cc is the territory's lead rep (same lookup as the tax-cert request), so
    the rep sees that their buyer was asked to sign. It may be empty when the
    territory is unknown — the admin fills it in before sending.

    expires_on is the token's own expiry, passed in rather than derived from a
    day count: the automatic chasers re-send this same body days later, and
    "expires in 30 days" would restart the clock in the reader's head every
    time. A date says the same thing on day 0 and day 4.
    """
    store = (account_name or "").strip()
    season = (season_label or "").strip()
    # "August 5" — no year. These links live weeks, not months, so the year is
    # noise; %-d drops the leading zero ("August 05" reads like a form field).
    expiry = f"{expires_on:%B} {expires_on.day}" if expires_on else ""

    # "Please review and sign your Fall 2026 order - ACME STORE - a3f19c47" —
    # wording and layout supplied by Wooden Ships (revised 2026-08-05); keep it
    # as written rather than re-phrasing. Store and id are appended with their
    # own separators so an order missing either doesn't leave a dangling dash.
    # The short id matches the other order mails (email/order_email.py) so every
    # message about one order sorts together in a mailbox.
    subject = " ".join(p for p in ("Please review and sign your", season, "order") if p)
    if store:
        subject = f"{subject} - {store}"
    if short_id:
        subject = f"{subject} - {short_id}"

    # "Hi there" rather than the buyer's name (2026-08-05): the Bill To name is
    # whoever signs, not necessarily whoever reads this at the store, and a
    # wrong first name reads worse than none. Matches the order copy's greeting
    # (email/order_email.py).
    #
    # **bold** / __underline__ are rendered in the HTML part and stripped from
    # the plain-text one — see app/email/mailer.py::html_from_text.
    body = f"""Hi there,

We have received your unsigned Draft Order! We appreciate it!

**Now we just need a signature!**

Please click on the link below to review, sign and submit.
{sign_url}

If you want to make changes, you can also do that before signing.

Note: The link will expire on __{expiry}__.

Ship Windows are not locked in until the order is received and accepted.
Please sign and submit right away to avoid missing a ship window.

If you have any questions, just reply to this email.

Thank you!
Wooden Ships
"""

    return {
        "to": (to_email or "").strip(),
        "cc": (cc_email or "").strip(),
        "subject": subject,
        "body": body,
    }
