"""The DMM recap text, laid out like the team's hand-written email (the
2026-10-26 one is the model). Pure layout: recap.py gathers the data.

It is pasted into WhatsApp, so it uses WhatsApp's markup: *bold* for each
group's title, and plain '- ' bullets."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from .steps import short

BULLET = "- "
_MODE_ORDER = {"AIR": 0, "FCL": 1, None: 2}


@dataclass
class Account:
    name: str
    rep: str | None  # first name, or 'House'
    note: str | None  # 'Wed, Oct 14 - <latest problem note>'
    last: str | None  # 'Mon, Oct 26 - Sent notice #4'
    plan: str | None  # 'Wed, Oct 28 - Send notice #5'


@dataclass
class Group:
    season: str  # 'F26'
    mode: str | None  # 'AIR' / 'FCL'
    window: str  # '10/01 - 10/15'
    start: date  # the window's first day
    sos: int
    qty: float
    amount: float
    last: str | None = None  # the window's last communication
    plan: str | None = None  # the window's next one
    accounts: list[Account] | None = None  # set = list each account instead of a Plan

    @property
    def title(self) -> str:
        words = [self.season, f"{self.start:%B}", self.mode]
        return f"*UNPAID {' '.join(w for w in words if w)} ({self.window}) order:*"  # WhatsApp bold


def sort_groups(groups: list[Group]) -> list[Group]:
    """By month, AIR before FCL, then the shorter window first."""
    return sorted(groups, key=lambda g: (g.start, _MODE_ORDER.get(g.mode, 2), g.window))


def _paid_lines(paid: list[tuple[str | None, date | str]], today: date) -> list[str]:
    """One bullet per (mode, ship date): AIR first, then FCL, each by date."""
    counts = Counter(paid)

    def key(item):
        (mode, ship), _ = item
        return (_MODE_ORDER.get(mode, 2), isinstance(ship, str), ship if isinstance(ship, date) else date.max)

    lines = []
    for (mode, ship), n in sorted(counts.items(), key=key):
        what = f"{n} {mode + ' ' if mode else ''}{'SOs' if n > 1 else 'SO'}"
        if isinstance(ship, date):
            lt = (ship - today).days
            when = f"on {short(ship)} (LT = {lt} {'day' if lt == 1 else 'days'}) at the latest"
        else:
            when = f"on {ship.strip() or 'a date not set yet'}"
        lines.append(f"{BULLET}For {what}, we plan to ship {'them' if n > 1 else 'it'} {when}.")
    return lines


def _group_lines(g: Group) -> list[str]:
    lines = [
        g.title,
        f"{BULLET}# of SO: {g.sos} SO, TTL Qty: {round(g.qty):,}, TTL Amount: ${round(g.amount):,}",
    ]
    if g.last:
        lines.append(f"{BULLET}Last communication: {g.last}.")
    if g.accounts is None:
        lines.append(f"{BULLET}Plan: {g.plan + '.' if g.plan else '(none scheduled)'}")
        return lines
    lines.append(f"{BULLET}Details as below:" if g.mode == "FCL" else f"{BULLET}Details per account as below:")
    for i, a in enumerate(g.accounts, 1):
        if i > 1:
            lines.append("")
        lines.append(f"{i}. {a.name}" + (f" ({a.rep})" if a.rep else ""))
        for text in (a.note, a.last):
            if text:
                lines.append(f"{BULLET}{text.rstrip('.')}.")
        lines.append(f"{BULLET}PLAN: {a.plan.rstrip('.') + '.' if a.plan else '(none scheduled)'}")
    return lines


def build(
    today: date,
    recipient: str,
    paid: list[tuple[str | None, date | str]],
    groups: list[Group],
) -> str:
    """The whole recap. paid: one (mode, planned ship date) per SO paid today."""
    n = len(paid)
    if n == 0:
        paid_intro = "Today, we have no orders that have been paid."
    elif n == 1:
        paid_intro = "Today, we have a total of 1 order that has been paid."
    else:
        paid_intro = f"Today, we have a total of {n} orders that have been paid."

    lines = [
        f"Hi {recipient},",
        "",
        f"Please see below the Daily Morning Meeting Update - {today:%A, %B} {today.day}, {today.year}.",
        "",
        "Confirming that today we had a daily morning meeting as scheduled.",
        "",
        paid_intro,
        *_paid_lines(paid, today),
        "",
        "Confirming that there are no charged orders from more than 3 days that have not yet shipped.",
        "",
    ]
    if groups:
        lines.append("Additionally, below is the total of the open orders that remain unpaid as of today.")
        for g in sort_groups(groups):
            lines += ["", *_group_lines(g)]
    else:
        lines.append("Additionally, there are no open orders that remain unpaid as of today.")
    lines += ["", "Thanks!"]
    return "\n".join(lines)
