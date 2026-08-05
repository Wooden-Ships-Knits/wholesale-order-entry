"""Draft email asking the buyer to review and sign their order.

Text only: this module never sends anything. The endpoint hands the draft to
the admin UI, where a human edits it and sends it (POST /api/send-email).

Unlike the conflict email this one goes to the CUSTOMER, so it names nothing
internal — no rep, no territory, no other stockists, no rank. It carries one
link, and that link is a credential: anyone the buyer forwards it to can edit
and sign the order. The body says so plainly rather than assuming the buyer
infers it.
"""


def build(
    *,
    to_email: str | None,
    sign_url: str,
    cc_email: str | None = None,
    account_name: str | None = None,
    season_label: str | None = None,
    total_qty: int | None = None,
    total_amount=None,
    expires_days: int = 7,
    short_id: str | None = None,
) -> dict:
    """-> {to, cc, subject, body}.

    cc is the territory's lead rep (same lookup as the tax-cert request), so
    the rep sees that their buyer was asked to sign. It may be empty when the
    territory is unknown — the admin fills it in before sending.
    """
    store = (account_name or "").strip()
    season = (season_label or "").strip()

    # "Please review and sign your Fall 2026 order ACME STORE" — wording and
    # layout supplied by Wooden Ships (2026-08-03); keep it as written rather
    # than re-phrasing. Both placeholders are dropped cleanly when empty. The
    # short id on the end matches the other order mails (email/order_email.py)
    # so every message about one order sorts together in a mailbox.
    subject = " ".join(
        p for p in ("Please review and sign your", season, "order", store) if p
    )
    if short_id:
        subject = f"{subject} - {short_id}"

    # "Hi there" rather than the buyer's name (2026-08-05): the Bill To name is
    # whoever signs, not necessarily whoever reads this at the store, and a
    # wrong first name reads worse than none. Matches the order copy's greeting
    # (email/order_email.py).
    body = f"""Hi there,

Thank you for your order! We appreciate it!

A copy of your order form is attached. Please Review your order, make any adjustments needed, and Sign to submit. Click the link below:
{sign_url}

The link will expire in {expires_days} days.

Ship Windows are not locked in until the order is received and accepted. Please sign and submit right away to avoid missing ship window.

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
