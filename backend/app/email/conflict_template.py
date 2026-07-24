"""Draft email to the sales rep when a new store trips the nearby-stockist
conflict check.

Text only: this module never sends anything. The endpoint hands the draft to
the admin UI, where a human edits it and sends it from their own mail client.

This email is INTERNAL — it goes to the rep, not the applicant — so it names
the conflicting stockists with drive time / distance / last-order season so the
rep can decide how to proceed (docs/conflict-checker.md).
"""
import re

_SEASON_RE = re.compile(r"[FS]\d{2}", re.IGNORECASE)


def _season(order_name: str | None) -> str:
    """Leading season code of a Salesforce order name, e.g.
    "F26 SWEATERS 11/01 - 11/20" -> "F26". "—" when there is none."""
    if not order_name:
        return "—"
    token = order_name.strip().split()[0]
    return token.upper() if _SEASON_RE.fullmatch(token) else "—"


def _metrics(neighbor: dict) -> str:
    """"8 min, 2.8 miles" when a drive time is known, else "2.8 miles"."""
    miles = neighbor.get("distanceMiles")
    minutes = neighbor.get("driveMinutes")
    miles_part = f"{miles} miles" if miles is not None else ""
    if minutes is not None:
        return ", ".join(p for p in (f"{minutes} min", miles_part) if p)
    return miles_part or "nearby"


def build(
    *,
    store_name: str | None = None,
    address: str | None = None,
    rep_name: str | None = None,  # accepted for API stability; no longer shown
    sales_territory: str | None = None,  # accepted for API stability; no longer shown
    state: str | None = None,  # accepted for API stability; no longer shown
    neighbors: list[dict] | None = None,
    to_email: str | None = None,
    max_minutes: int = 20,
) -> dict:
    """-> {to, subject, body}. Every field is optional so the draft can be
    generated from a bare conflict-check result as well as from an order."""
    store = (store_name or "").strip()
    address = (address or "").strip()
    neighbors = neighbors or []

    subject = "CONFLICT Inquiry — [store name]"
    if store:
        subject = f"CONFLICT Inquiry — {store}"

    # One line per paragraph — the mail client wraps it. Two blocks keep their
    # own newlines (they are meaningful): the account block and the bullet list.
    paragraphs = [
        "Hi,",
        "We received an order from this account.",
    ]

    account_block = "\n".join(line for line in (store, address) if line)
    if account_block:
        paragraphs.append(account_block)

    if neighbors:
        bullets = "\n".join(
            f"  • {n.get('name') or '(unnamed account)'} "
            f"({_metrics(n)}) - Last order: {_season(n.get('lastOrderName'))}"
            for n in neighbors
        )
        paragraphs.append(
            "There are potential conflicts with the following accounts:"
            f"\n\n{bullets}"
        )
        paragraphs.append(
            "Please review this potential conflict and let us know if we may proceed."
        )
        paragraphs.append("Thanks!")
    else:
        paragraphs.append("No nearby stockist conflicts were found for this inquiry.")

    body = "\n\n".join(paragraphs)
    return {"to": (to_email or "").strip(), "subject": subject, "body": body}
