"""Draft email to the sales rep when a new store trips the nearby-stockist
conflict check.

Text only: this module never sends anything. The endpoint hands the draft to
the admin UI, where a human edits it and sends it from their own mail client.

This email is INTERNAL — it goes to the rep, not the applicant — so it names
the conflicting stockists with drive time / distance / last-order season so the
rep can decide how to proceed (docs/conflict-checker.md).
"""
import re

GREETING_FALLBACK = "Hi team"
_SEASON_RE = re.compile(r"[FS]\d{2}", re.IGNORECASE)


def _rep_from_territory(territory: str | None) -> str | None:
    """Rep name out of a Sales Territory value like "New England - Kitty Tally"
    -> "Kitty Tally" (everything after the " - "). None when there is no such
    delimiter, so the caller can fall back to the rep field."""
    if not territory or " - " not in territory:
        return None
    name = territory.split(" - ", 1)[1].strip()
    return name or None


def _greeting(rep_name: str | None, sales_territory: str | None = None) -> str:
    """"Hi <name>," line. Prefers the rep named in the Sales Territory field
    (kept in full, e.g. "Hi Kitty Tally"); otherwise the first name from the
    rep field; otherwise the team fallback."""
    territory_rep = _rep_from_territory(sales_territory)
    if territory_rep:
        return f"Hi {territory_rep}"
    if rep_name and rep_name.strip():
        return f"Hi {rep_name.strip().split()[0]}"
    return GREETING_FALLBACK


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
    rep_name: str | None = None,
    sales_territory: str | None = None,
    state: str | None = None,
    neighbors: list[dict] | None = None,
    to_email: str | None = None,
    max_minutes: int = 20,
) -> dict:
    """-> {to, subject, body}. Every field is optional so the draft can be
    generated from a bare conflict-check result as well as from an order."""
    store = (store_name or "").strip()
    neighbors = neighbors or []

    subject = "Wooden Ships wholesale inquiry — potential conflict nearby"
    if store:
        subject = f"Wooden Ships wholesale inquiry — {store} (potential conflict nearby)"

    store_phrase = store or "a new store"
    conflict_line = (
        f"There are potential conflicts according to the state ({state.strip()}) "
        "with the following accounts:"
        if state
        else "There are potential conflicts nearby with the following accounts:"
    )

    # One line per paragraph — the mail client wraps it. The bullet block is the
    # exception: its newlines are meaningful, so it is joined into one paragraph.
    paragraphs = [
        f"{_greeting(rep_name, sales_territory)},",
        f"Please see the wholesale inquiry below from {store_phrase}.",
    ]
    if neighbors:
        bullets = "\n".join(
            f"  • {n.get('name') or '(unnamed account)'} "
            f"({_metrics(n)}) - Last order: {_season(n.get('lastOrderName'))}"
            for n in neighbors
        )
        paragraphs.append(f"{conflict_line}\n\n{bullets}")
        paragraphs.append(
            "Please reach out to the account if you would like to work with them."
        )
        # Add thanks
        paragraphs.append("Thanks!")
    else:
        paragraphs.append("No nearby stockist conflicts were found for this inquiry.")

    body = "\n\n".join(paragraphs)
    return {"to": (to_email or "").strip(), "subject": subject, "body": body}
