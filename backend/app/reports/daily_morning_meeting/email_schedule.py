"""Which chase email was last sent to reps for each ship window."""
import re
from datetime import date

import pandas as pd

from app.config import settings
from app.sheets import client as sheets

WORKSHEET = "Email Schedule"

# Pulls the two month/day pairs out of a ship-window string, tolerating
# zero-padding ('06/01') and not ('6/1').
_RANGE_RE = re.compile(r'(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})')


def _range_key(text):
    """'06/01 - 06/30' or '6/1 - 6/30' -> (6, 1, 6, 30); None if no range found."""
    if not isinstance(text, str):
        return None
    m = _RANGE_RE.search(text)
    return tuple(int(x) for x in m.groups()) if m else None


def _email_date_cols(df):
    """[(column, label)] for each EMAIL #N / FOLLOW UP EMAIL #N column, in send order.

    Column order in the sheet is the send order (#1..#7 then the rep follow-up),
    so we just keep the columns as they appear. 'Reply to All...' columns are skipped.
    """
    cols = []
    for c in df.columns:
        cu = c.upper()
        if 'REPLY' in cu:
            continue
        m = re.search(r'EMAIL\s*#\s*(\d)', cu)
        if not m:
            continue
        n = m.group(1)
        label = f'Sent follow-up email #{n} to rep' if 'FOLLOW UP' in cu else f'Sent email #{n}'
        cols.append((c, label))
    return cols


_LOOKUP = None


def _build_lookup():
    """{range_key: [(label, date), ...]} for the current year, keyed by ship window.

    Later rows overwrite earlier ones so 'UPDATED PLAN' rows win over 'INITIAL PLAN'.
    """
    if not settings.problem_list_reps_sheet_id:
        raise RuntimeError("PROBLEM_LIST_REPS_SHEET_ID is not set")
    # UNFORMATTED_VALUE so the send dates arrive as Google serial numbers,
    # which the conversion below expects.
    values = sheets.get_values(
        settings.problem_list_reps_sheet_id,
        WORKSHEET,
        value_render_option="UNFORMATTED_VALUE",
    )
    if len(values) < 7:
        raise RuntimeError(f"Worksheet {WORKSHEET!r} has no data rows")
    df = pd.DataFrame(values[6:], columns=values[4])

    email_cols = _email_date_cols(df)
    for c, _ in email_cols:
        nums = pd.to_numeric(df[c], errors='coerce')                       # Google serial -> date
        df[c] = (pd.Timestamp('1899-12-30') + pd.to_timedelta(nums, unit='D')).dt.date

    this_year = date.today().year
    first_col = email_cols[0][0]

    lookup = {}
    for _, row in df.iterrows():
        key = _range_key(row['SHIP WINDOW'])
        if key is None:
            continue
        first = row[first_col]                                             # email #1 anchors the year
        if pd.isna(first) or first.year != this_year:
            continue
        lookup[key] = [(label, row[c]) for c, label in email_cols if pd.notna(row[c])]
    return lookup


def sentEmailLine(range_text, today=None):
    """'Sent email #N:  <Weekday, Month D>' for the most recent email sent on/before
    today for this ship window. None if the range isn't found or nothing sent yet.

    Past months resolve to follow-up #7 (all emails are already sent); the ongoing
    month resolves to whichever email is the closest one on/before today.
    """
    global _LOOKUP
    if _LOOKUP is None:
        _LOOKUP = _build_lookup()

    today = today or date.today()
    key = _range_key(range_text)
    if key is None:
        return None
    dates = _LOOKUP.get(key)
    if not dates:
        return None
    sent = [(label, d) for label, d in dates if d <= today]
    if not sent:
        return None
    label, d = max(sent, key=lambda x: x[1])
    return f"{label}:  {d.strftime('%A, %B ')}{d.day}"
