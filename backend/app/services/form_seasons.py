"""Which of the 3 newest seasons the order form shows, as ticked in /admin.

The order form offers the CANDIDATES newest seasons (by active wholesale price
book). /admin -> Catalog lists those same seasons with a checkbox; unticking
one hides it from the form.

What is saved is the UNTICKED set, as a JSON list in settings.form_seasons_file
(e.g. ["S26"]). Storing what's hidden rather than what's shown means a season
that newly becomes one of the 3 newest appears on its own, and no file at all
means "show all 3". Codes that have aged out of the 3 are dropped on the next
save.

At least one season must stay ticked: a form with an empty collection picker
can't take an order.

Merchandising, not access control (same as hidden_products): POST /api/orders
does not reject a season unticked after the buyer opened the form.
"""
import json
import logging
import os
import threading
from collections.abc import Iterable
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

CANDIDATES = 3

# One backend process, so a lock keeps two admins' clicks from interleaving a
# read-modify-write.
_lock = threading.Lock()


class LastSeasonError(ValueError):
    """Unticking would leave the order form with no collection."""


class NotACandidateError(ValueError):
    """The season isn't one of the 3 newest, so it has no checkbox."""


def _path() -> Path:
    return Path(settings.form_seasons_file)


def hidden_codes() -> set[str]:
    """Seasons unticked in /admin. Empty when nothing was saved — or when the
    file can't be read, so the form shows all 3 rather than going blank."""
    try:
        data = json.loads(_path().read_text())
    except FileNotFoundError:
        return set()
    except (OSError, ValueError):
        logger.warning("Could not read %s; showing all newest seasons", _path(), exc_info=True)
        return set()
    return {str(c) for c in data} if isinstance(data, list) else set()


def _write(codes: set[str]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(codes)))
    os.replace(tmp, path)  # atomic: a reader never sees half a file


def candidates(all_codes_newest_first: Iterable[str]) -> list[str]:
    """The seasons that get a checkbox: the 3 newest."""
    return list(all_codes_newest_first)[:CANDIDATES]


def shown(candidate_codes: Iterable[str], hidden: set[str]) -> list[str]:
    """The candidates the order form shows, newest first. Pure."""
    return [c for c in candidate_codes if c not in hidden]


def set_shown(code: str, on: bool, candidate_codes: list[str]) -> list[str]:
    """Tick or untick one candidate. Idempotent. Returns what the form shows."""
    if code not in candidate_codes:
        raise NotACandidateError(f"{code} is not one of the {CANDIDATES} newest collections.")
    with _lock:
        hidden = hidden_codes() & set(candidate_codes)
        hidden = hidden - {code} if on else hidden | {code}
        if not shown(candidate_codes, hidden):
            raise LastSeasonError("At least one collection has to stay on the order form.")
        _write(hidden)
    logger.info("Order form seasons: %s %s", "shown" if on else "hidden", code)
    return shown(candidate_codes, hidden)
