"""Where each ship window's chase emails stand, from the "Email Schedule" tab.

One row per ship window and year (plus "UPDATED" rows that re-plan an earlier
one); one column per step in send order: CC notification, email #1, its
"Reply to All" follow-up, email #2, … email #8 or more, then the cancel date.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.config import settings
from app.sheets import client as sheets

from .steps import Step, step_name

WORKSHEET = "Email Schedule"

# Pulls the two month/day pairs out of a ship-window string, tolerating
# zero-padding ('06/01') and not ('6/1').
_RANGE_RE = re.compile(r'(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})')

# Rows of one window this far apart belong to different years' cycles.
_SAME_CYCLE = timedelta(days=60)


def range_key(text: object) -> tuple[int, int, int, int] | None:
    """'06/01 - 06/30' or '6/1 - 6/30' -> (6, 1, 6, 30); None if no range found."""
    m = _RANGE_RE.search(str(text or ""))
    return tuple(int(x) for x in m.groups()) if m else None


@dataclass
class Status:
    last: Step | None  # most recent step on or before today
    next: Step | None  # first step after today
    ended: bool  # no email left before the cancel date


class Schedule:
    """The Email Schedule tab, read once per DMM run (never cached across runs:
    the team edits it, and an old copy would report the wrong emails)."""

    def __init__(self, values: list[list], today: date):
        self.today = today
        self._rows: dict[tuple, list[list[Step]]] = {}
        if len(values) < 7:
            raise RuntimeError(f"Worksheet {WORKSHEET!r} has no data rows")
        header = values[4]
        window = next(i for i, h in enumerate(header) if "SHIP WINDOW" in str(h).upper())
        columns = [(i, name) for i, h in enumerate(header) if (name := step_name(h))]
        for row in values[6:]:
            key = range_key(row[window] if window < len(row) else "")
            if key is None:
                continue
            steps = [Step(_serial(row[i]), name) for i, name in columns if i < len(row) and _serial(row[i])]
            if steps:
                self._rows.setdefault(key, []).append(steps)

    @classmethod
    def load(cls, today: date) -> "Schedule":
        if not settings.problem_list_reps_sheet_id:
            raise RuntimeError("PROBLEM_LIST_REPS_SHEET_ID is not set")
        # UNFORMATTED_VALUE: dates arrive as Google serial numbers, unambiguous
        # whatever way the cell is formatted ('Mon, Oct 26' / 'Tue,  26, Dec').
        return cls(
            sheets.get_values(settings.problem_list_reps_sheet_id, WORKSHEET, value_render_option="UNFORMATTED_VALUE"),
            today,
        )

    def status(self, window: str) -> Status | None:
        """The window's position in its schedule today; None if it has no row.

        The tab keeps every year's rows, so the row used is the one whose first
        step is closest to today — and among rows of that cycle the last one,
        since an "UPDATED" plan sits below the plan it replaces.
        """
        rows = self._rows.get(range_key(window))
        if not rows:
            return None
        anchor = min((r[0].day for r in rows), key=lambda d: abs(d - self.today))
        steps = [r for r in rows if abs(r[0].day - anchor) <= _SAME_CYCLE][-1]
        done = [s for s in steps if s.day <= self.today]
        ahead = [s for s in steps if s.day > self.today]
        return Status(
            last=max(done, key=lambda s: s.day) if done else None,
            next=min(ahead, key=lambda s: s.day) if ahead else None,
            ended=not ahead,
        )


def _serial(value: object) -> date | None:
    """A Google Sheets serial day number as a date; None for text ('N/A', '#REF!')."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return date(1899, 12, 30) + timedelta(days=int(value))
