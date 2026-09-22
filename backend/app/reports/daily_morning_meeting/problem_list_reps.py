"""Today's shipping plan, from the Problem List Reps sheet."""
import logging
from datetime import date

import pandas as pd

from app.config import settings
from app.sheets import client as sheets

logger = logging.getLogger(__name__)

WORKSHEET = "WHOLESALE Paid Open Orders"
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


def problemListReps() -> tuple[int, pd.DataFrame]:
    """(paid SOs updated today, SO counts grouped by planned ship date).

    The sheet's header is row 3 and data starts at row 4 — hence values[2] as
    the columns and values[3:] as the rows.
    """
    if not settings.problem_list_reps_sheet_id:
        raise RuntimeError("PROBLEM_LIST_REPS_SHEET_ID is not set")

    values = sheets.get_values(settings.problem_list_reps_sheet_id, WORKSHEET)
    if len(values) < 4:
        raise RuntimeError(f"Worksheet {WORKSHEET!r} has no data rows")

    df = pd.DataFrame(values[3:], columns=values[2])
    markers = _today_markers(date.today())
    seen = {str(v).strip() for v in df["Update Date"] if str(v).strip()}
    df = df[df["Update Date"].map(lambda v: _norm(v) in markers)]

    total_sos = len(df["Update Date"])
    if not total_sos:
        # A genuinely quiet day and a sheet whose date format moved again both
        # print "0 SO". Say which in the log, so the next drift is one line to
        # find rather than a re-run with a debugger.
        logger.warning(
            "No rows in %r are marked %s — the recap will report 0 paid SOs. "
            "Update Date values present: %s",
            WORKSHEET, sorted(markers), sorted(seen)[:8],
        )

    df = df.assign(**{"SO qty": 1})
    # Sum only the counter: a bare .sum() over the whole frame would try to add
    # the text columns too, which pandas 2 refuses.
    df_ship = df.groupby(SHIP_DATE_COL)[["SO qty"]].sum()

    return total_sos, df_ship
