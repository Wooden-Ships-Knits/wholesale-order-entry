"""Shared vocabulary of the DMM sheets: their year-less dates, and the chase
steps (email #3, follow-up email #2, …) named by their column headers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

_DAY_MONTH = re.compile(r"^\s*(\d{1,2})-([A-Za-z]{3})")  # '26-Oct' (problem-list tabs)
_MONTH_DAY = re.compile(r"(\d{1,2})/(\d{1,2})")  # '10/28' ('Send on 10/28', notes)
_NAMED = re.compile(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2})\b")  # 'Wed, Oct 28' (paid tab)


def nearest(month: int, day: int, today: date) -> date | None:
    """The date with this month/day closest to today. The sheets never write a
    year, and a December date read in January belongs to last year."""
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((d - today).days) < abs((best - today).days):
            best = d
    return best


def parse(text: object, today: date) -> date | None:
    """A sheet date in any of the spellings the team uses, or None."""
    s = str(text or "")
    if m := _DAY_MONTH.match(s):
        month = _MONTHS.get(m.group(2).lower())
        return nearest(month, int(m.group(1)), today) if month else None
    if m := _MONTH_DAY.search(s):
        return nearest(int(m.group(1)), int(m.group(2)), today)
    for m in _NAMED.finditer(s):
        if month := _MONTHS.get(m.group(1).lower()):
            return nearest(month, int(m.group(2)), today)
    return None


def short(d: date) -> str:
    """'Wed, Oct 28' — how the recap writes every date but its own."""
    return f"{d:%a, %b} {d.day}"


def step_name(header: str) -> str | None:
    """'email #3', 'follow-up email #2', … for a chase-email column header of
    the Email Schedule or a month tab; None for any other column.

        EMAIL  #1 / email 1                          -> email #1
        Reply to All - to follow up for email #2     -> follow-up email #2
        Follup Email #2                              -> follow-up email #2
        Reply to All - 2nd follow up for email #5    -> 2nd follow-up email #5
        FOLLOW UP EMAIL #7 To Rep & Cust             -> follow-up email #7 to rep & cust
        EMAIL CC NOTIFICATION / email CC notif       -> CC notification email

    Charging, the problem list forwarded to the rep, and the cancel date are not
    emails to the customer, so they are not steps.
    """
    h = " ".join(str(header).split()).lower()
    if "cc notif" in h:
        return "CC notification email"
    m = re.search(r"#\s*(\d+)", h) or re.search(r"^email\s+(\d+)$", h)
    if not m:
        return None
    n = m.group(1)
    if "2nd follow" in h:
        return f"2nd follow-up email #{n}"
    if "follow" in h or "follup" in h:
        # "to rep" / "(rep & cust)", not the "rep" in "Reply to All".
        to_rep = re.search(r"\brep\b", h)
        return f"follow-up email #{n} to rep & cust" if to_rep else f"follow-up email #{n}"
    if h.startswith("email"):
        return f"email #{n}"
    return None


@dataclass(frozen=True)
class Step:
    day: date
    name: str  # from step_name()

    def worded(self, done: bool, fcl: bool = False) -> str:
        """'Mon, Oct 26 - Sent email #8' / 'Wed, Oct 28 - Send notice #5'.
        FCL orders are chased with notices, not emails."""
        name = self.name.replace("email #", "notice #") if fcl else self.name
        return f"{short(self.day)} - {'Sent' if done else 'Send'} {name}"
