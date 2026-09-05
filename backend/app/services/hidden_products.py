"""Which style+colors the admin has taken off the order form.

FLAGGED, NOT DROPPED. /api/products marks a hidden row and still returns it.
The signing page rebuilds a saved draft's lines by matching style+color against
this same catalogue (frontend/src/sign/SignPage.jsx), so a row that vanished
would take the draft's unit price, line total and minimum-check with it --
hiding a style would silently gut every order already out for signature. The
order form filters its own picker instead (components/ProductLines.jsx), which
is the only place the distinction is supposed to be visible.

That makes this merchandising, not access control: a crafted API call can still
order a hidden style. Deliberate. The rules that must actually hold -- the order
minimums -- are enforced in app/validation, on the server, on submit.
"""
import logging
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import HiddenProduct

logger = logging.getLogger(__name__)

# One catalogue row's identity, and the natural key of `hidden_products`.
Key = tuple[str, str]


def hidden_keys(db: Session, season: str) -> set[Key]:
    """(style, color) pairs hidden for one season."""
    rows = db.execute(
        select(HiddenProduct.style_name, HiddenProduct.color).where(
            HiddenProduct.season_code == season
        )
    ).all()
    return {(r.style_name, r.color) for r in rows}


def flag_rows(rows: Iterable[dict[str, Any]], keys: set[Key]) -> list[dict[str, Any]]:
    """Stamp row["hidden"] on each catalogue row. Pure -- no database, so the
    behaviour that matters (every row survives, flagged) is testable without
    Postgres."""
    out = list(rows)
    for row in out:
        row["hidden"] = (row["styleName"], row["color"]) in keys
    return out


def set_hidden(db: Session, season: str, style_name: str, color: str, hidden: bool) -> bool:
    """Hide or unhide one style+color. Idempotent in both directions -- clicking
    an already-checked box is not an error, and two admins with the tab open
    cannot produce a duplicate or a stuck row. Returns the resulting state."""
    if hidden:
        db.execute(
            insert(HiddenProduct)
            .values(season_code=season, style_name=style_name, color=color)
            .on_conflict_do_nothing()
        )
    else:
        db.execute(
            delete(HiddenProduct).where(
                HiddenProduct.season_code == season,
                HiddenProduct.style_name == style_name,
                HiddenProduct.color == color,
            )
        )
    db.commit()
    logger.info(
        "Catalog: %s %s / %s (%s)",
        "hid" if hidden else "un-hid",
        style_name,
        color,
        season,
    )
    return hidden
