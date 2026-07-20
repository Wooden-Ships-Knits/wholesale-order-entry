"""Draft email for a store that failed the nearby-stockist conflict check.

Text only: this module never sends anything. The endpoint hands the draft to
the admin UI, where a human edits it and sends it from their own mail client.

The body is addressed to the *applicant*, so it never names the conflicting
stockists — who they are is internal (docs/conflict-checker.md).
"""

GREETING_FALLBACK = "Hello"


def _first_name(contact_name: str | None) -> str:
    if not contact_name:
        return GREETING_FALLBACK
    return f"Hi {contact_name.strip().split()[0]}"


def _location_phrase(address: str | None) -> str:
    return f"the area around {address.strip()}" if address else "that area"


def build(
    *,
    store_name: str | None = None,
    contact_name: str | None = None,
    to_email: str | None = None,
    address: str | None = None,
    rep_name: str | None = None,
    max_minutes: int = 20,
) -> dict:
    """-> {to, subject, body}. Every field is optional so the draft can be
    generated from a bare conflict-check result as well as from an order."""
    store = (store_name or "").strip()
    subject = "Wooden Ships wholesale — your account inquiry"
    if store:
        subject = f"Wooden Ships wholesale — inquiry for {store}"

    store_clause = f" at {store}" if store else ""
    signature = (rep_name or "").strip() or "The Wooden Ships Team"
    # One line per paragraph — the mail client wraps it, and hard-wrapping here
    # produces ragged lines once the store name and address are interpolated.
    paragraphs = [
        f"{_first_name(contact_name)},",
        f"Thank you for your interest in carrying Wooden Ships{store_clause}.",
        (
            "We protect the territories of the retailers who carry our collection, and we "
            f"already have a stockist serving {_location_phrase(address)} — within about a "
            f"{max_minutes}-minute drive. Because of that we are not able to open a new "
            "wholesale account at this address right now."
        ),
        (
            "If you have another location outside that radius, or if your store serves a "
            "distinctly different customer, please reply and let us know — we are glad to "
            "take a second look."
        ),
        "We appreciate you thinking of Wooden Ships and hope we can work together in the future.",
        f"Warm regards,\n{signature}\nWooden Ships",
    ]
    body = "\n\n".join(paragraphs)

    return {"to": (to_email or "").strip(), "subject": subject, "body": body}
