"""Today's shipping plan, from the Problem List Reps sheet."""
from datetime import date

import pandas as pd

from app.config import settings
from app.sheets import client as sheets

WORKSHEET = "WHOLESALE Paid Open Orders"
SHIP_DATE_COL = "Planned Ship Date\n(Bali time)"


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
    # The sheet writes today's marker with a trailing space ("Mon, Jul 28 ").
    df = df[df["Update Date"] == date.today().strftime("%a, %b %d ")]

    total_sos = len(df["Update Date"])
    df = df.assign(**{"SO qty": 1})
    # Sum only the counter: a bare .sum() over the whole frame would try to add
    # the text columns too, which pandas 2 refuses.
    df_ship = df.groupby(SHIP_DATE_COL)[["SO qty"]].sum()

    return total_sos, df_ship
