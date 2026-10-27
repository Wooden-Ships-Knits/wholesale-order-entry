"""Today's paid orders and their planned ship dates, from the Problem List Reps
sheet."""
import logging
from datetime import date

from app.config import settings
from app.sheets import client as sheets

logger = logging.getLogger(__name__)

WORKSHEET = "WHOLESALE Paid Open Orders"
ORDER_COL = "Order: Order Number"
SHIP_DATE_COL = "Planned Ship Date\n(Bali time)"


def _today_markers(today: date) -> set[str]:
    """The spellings of today's "Update Date" marker we accept, normalised.

    The column is typed/filled by hand in the sheet, so its exact text drifts.
    It was once written with a trailing space ("Mon, Jul 28 ") and the filter
    used to compare against exactly that — on 2026-09-22 the trailing space was
    gone, every row missed, and the recap reported 0 paid SOs when the sheet
    held 10. Match on a normalised form instead of one literal, and accept the
    day both zero-padded and not ("Sep 02" / "Sep 2"), since strftime pads and
    the sheet does not.
    """
    return {
        _norm(today.strftime("%a, %b %d")),
        _norm(today.strftime("%a, %b ") + str(today.day)),
    }


def _norm(text: object) -> str:
    """Collapse whitespace and case so two spellings of a date compare equal."""
    return " ".join(str(text).split()).casefold()


def paid_today(today: date) -> list[tuple[str, str]]:
    """[(SO number, planned ship date as typed)] for the rows updated today.

    The sheet's header is row 3 and data starts at row 4.
    """
    if not settings.problem_list_reps_sheet_id:
        raise RuntimeError("PROBLEM_LIST_REPS_SHEET_ID is not set")

    values = sheets.get_values(settings.problem_list_reps_sheet_id, WORKSHEET)
    if len(values) < 4:
        raise RuntimeError(f"Worksheet {WORKSHEET!r} has no data rows")

    header = values[2]
    update, order, ship = (header.index(c) for c in ("Update Date", ORDER_COL, SHIP_DATE_COL))
    markers = _today_markers(today)
    rows = [r for r in values[3:] if _norm(r[update]) in markers]

    if not rows:
        # A genuinely quiet day and a sheet whose date format moved again both
        # print "no orders". Say which in the log, so the next drift is one line
        # to find rather than a re-run with a debugger.
        seen = sorted({str(r[update]).strip() for r in values[3:] if str(r[update]).strip()})
        logger.warning(
            "No rows in %r are marked %s — the recap will report no paid SOs. "
            "Update Date values present: %s",
            WORKSHEET, sorted(markers), seen[:8],
        )
    return [(r[order].strip(), r[ship]) for r in rows]
