"""The latest problem note for an order, from the rep tabs of the Problem List
Reps sheet ("Jason", "Rande", …).

Each order sits on its rep's tab with a PROBLEM NOTES cell of dated lines,
newest last:

    10/14 - The rep will certainly contact the cust.
    10/21 - The rep has reached out to the cust.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from app.config import settings
from app.sheets import client as sheets

from .steps import nearest, short

logger = logging.getLogger(__name__)

# One tab per rep, plus House accounts that deal with us directly. A rep added
# to the sheet needs adding here.
REP_TABS = ("Aviva", "Amanda", "Denise", "Jason", "Kitty", "Michael", "Rande", "Vickie", "No Rep")

# '10/14 - text' — the text must have a letter, so a ship window ('10/01 - 10/30') is not a note.
_NOTE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*-\s*(.*[A-Za-z].*?)\s*$")


def latest(numbers: set[str], today: date) -> dict[str, str]:
    """{SO number: 'Wed, Oct 14 - <note>'} for the orders that have a note."""
    found: dict[str, tuple[date, str]] = {}
    for tab in REP_TABS:
        try:
            values = sheets.get_values(settings.problem_list_reps_sheet_id, tab)
        except Exception:
            logger.warning("Rep tab %r could not be read", tab, exc_info=True)
            continue
        for number, day, text in notes_in(values, numbers, today):
            if number not in found or day >= found[number][0]:
                found[number] = (day, text)
    return {n: f"{short(d)} - {t}" for n, (d, t) in found.items()}


def notes_in(values: list[list], numbers: set[str], today: date):
    """(SO number, date, text) for every dated note on a row of these orders."""
    for row in values:
        cells = [str(c).strip() for c in row]
        for number in numbers.intersection(cells):
            for cell in cells:
                for line in cell.splitlines():
                    m = _NOTE.match(line)
                    if m and (day := nearest(int(m.group(1)), int(m.group(2)), today)):
                        yield number, day, m.group(3)
