"""Each unpaid order's own chase emails, from the month tabs ("OCT", "NOV", …)
of the Problem List Reps sheet.

One row per order; one column per step ("email 1", "Follup Email #2", …). A
cell holds the date it was sent ('26-Oct'), a plan ('Send on 10/28',
'Charge on 11/3'), free text ('Send after oct order deliv.'), or '-' for a
step that was skipped.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from app.config import settings
from app.sheets import client as sheets

from .steps import Step, parse, short, step_name

logger = logging.getLogger(__name__)

ORDER_COL = "Order: Order Number"
_SENT = re.compile(r"^\s*\d{1,2}-[A-Za-z]{3}\s*$")  # '26-Oct'
_PLANNED = re.compile(r"^\s*(send|charge)\s+on\b", re.I)  # 'Send on 10/28'
_EMPTY = {"", "-", "v", "n/a", "#n/a"}


@dataclass
class OrderSteps:
    last: Step | None  # the latest step sent, on or before today
    plan: Step | None  # the next step with a planned date
    plan_text: str | None  # what the sheet says is next, when it's not a dated step
    charge_on: date | None = None  # 'Charge on 11/3'

    def plan_worded(self, fcl: bool) -> str | None:
        if self.charge_on:
            return f"{short(self.charge_on)} - Charge the order"
        if self.plan:
            return self.plan.worded(done=False, fcl=fcl)
        return self.plan_text


def tab_name(month: int) -> str:
    """The month tab holding a ship window's orders: 10 -> 'OCT'."""
    return date(2000, month, 1).strftime("%b").upper()


def read(month: int, today: date) -> dict[str, OrderSteps]:
    """{SO number: OrderSteps} for one month tab; empty if the tab is missing."""
    try:
        values = sheets.get_values(settings.problem_list_reps_sheet_id, tab_name(month))
    except Exception:  # a tab not created yet — the run carries on without it
        logger.warning("Month tab %r could not be read", tab_name(month), exc_info=True)
        return {}
    return parse_tab(values, today)


def parse_tab(values: list[list], today: date) -> dict[str, OrderSteps]:
    """The month tab's rows by SO number. Its header is row 2."""
    if len(values) < 3:
        return {}
    header = values[1]
    order = header.index(ORDER_COL)
    columns = [(i, name) for i, h in enumerate(header) if (name := step_name(h))]

    out = {}
    for row in values[2:]:
        number = str(row[order]).strip() if order < len(row) else ""
        if not number.startswith("SO-"):
            continue
        sent: list[Step] = []
        plan = plan_text = charge_on = None
        for i, name in columns:
            cell = str(row[i]).strip() if i < len(row) else ""
            if cell.casefold() in _EMPTY:
                continue
            day = parse(cell, today)
            if _SENT.match(cell) and day and day <= today:
                sent.append(Step(day, name))
            elif plan is None and plan_text is None and charge_on is None:
                # The first cell that isn't a sent date is what comes next.
                if _PLANNED.match(cell) and day:
                    if cell.lower().startswith("charge"):
                        charge_on = day
                    else:
                        plan = Step(day, name)
                elif _SENT.match(cell) and day:  # a date typed ahead of time
                    plan = Step(day, name)
                else:
                    plan_text = cell
        out[number] = OrderSteps(
            last=max(sent, key=lambda s: s.day) if sent else None,
            plan=plan,
            plan_text=plan_text,
            charge_on=charge_on,
        )
    return out
