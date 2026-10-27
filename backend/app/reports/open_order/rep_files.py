"""Split the OO report into one file per rep, plus a House file.

THIS LIST IS THE RULE. Each rep file names the Sales Territories it holds, and
which sheet each goes on; adding a rep or moving a territory is an edit here.
A territory that appears in Salesforce but in no file here stops the run (by
decision 2026-10-27) — better no files than a rep silently missing orders.

Split orders: an order whose Split With names another rep is ALSO copied into
that rep's file, in a "Split orders" section below their own orders. A rep who
splits with themselves gets no second copy. A rep with two sheets receives the
copy on the sheet for its ship-to state (Jason: FL → FL sheet; Kitty: NY → NY
sheet), otherwise on their first sheet — the team's own practice in the
2026-10-26 files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .workbook import TERRITORY, Order, SheetSpec, by_number

SPLIT_WITH = "kugo2p__SalesOrder__c.Split_With__c"
SHIP_STATE = "kugo2p__SalesOrder__c.kugo2p__ShipToStateProvince__c"


@dataclass(frozen=True)
class Sheet:
    name: str  # Excel sheet name (max 31 chars, no "/")
    territories: tuple[str, ...]
    # Split copies shipping to one of these states land on this sheet.
    split_states: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RepFile:
    area: str  # the area part of the file name
    rep: str | None  # full name as Salesforce writes it in Split With; None = House
    short: str | None  # the name at the end of the file name
    sheets: tuple[Sheet, ...]

    def filename(self, day: date) -> str:
        stamp = f"{day:%y%m%d}"
        if self.short:
            return f"OO-{self.area}-YTD-{stamp}-{self.short}.xlsx"
        return f"OO-{self.area}-YTD-{stamp}.xlsx"


def _one(name: str, territory: str) -> tuple[Sheet, ...]:
    return (Sheet(name, (territory,)),)


FILES: tuple[RepFile, ...] = (
    RepFile("CA,HI", "Rande Cohen", "Rande", _one("CA, HI - Rande Cohen", "CA/HI - Rande Cohen")),
    RepFile(
        "Mid Atlantic", "Michael Young", "Michael",
        _one("Mid Atlantic - Michael Young", "Mid Atlantic - Michael Young"),
    ),
    RepFile("Midwest", "Aviva Landin", "Aviva", _one("Midwest - Aviva Landin", "Midwest - Aviva Landin")),
    RepFile("Mountain", "Denise Arnett", "Denise", _one("Mountain - Denise Arnett", "Mountain - Denise Arnett")),
    RepFile(
        "New England, NY", "Kitty Tally", "Kitty",
        (
            Sheet("New England - Kitty Tally", ("New England - Kitty Tally",)),
            Sheet(
                "NY - Kitty Tally",
                ("Upstate NY - Kitty Tally", "Long Island - Kitty Tally"),
                frozenset({"NY"}),
            ),
        ),
    ),
    RepFile(
        "New York", "Amanda Santoro", "Amanda",
        _one("Upstate NY - Amanda Santoro", "Upstate NY - Amanda Santoro"),
    ),
    RepFile("South", "Vickie Wilde", "Vickie", _one("South - Vickie Wilde", "South - Vickie Wilde")),
    RepFile(
        "Southeast, FL", "Jason Hilsenrad", "Jason",
        (
            Sheet("Southeast - Jason Hilsenrad", ("Southeast - Jason Hilsenrad",)),
            Sheet("FL - Jason Hilsenrad", ("FL - Jason Hilsenrad",), frozenset({"FL"})),
        ),
    ),
    # House and unassigned territories — no rep of their own. "" = no territory.
    RepFile(
        "House", None, None,
        (Sheet("House", ("AK / AZ / NE / NV", "NM/MT - House", "Pacific Northwest - House", "")),),
    ),
)


class UnknownTerritory(RuntimeError):
    """A territory or Split With rep that no file covers — the run stops."""


def _norm(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


@dataclass
class _Target:
    file: RepFile
    sheet: Sheet
    own: list[Order] = field(default_factory=list)
    split: list[Order] = field(default_factory=list)


def split_orders(orders: list[Order]) -> list[tuple[RepFile, list[SheetSpec]]]:
    """Every file's sheets, filled. Raises UnknownTerritory naming whatever
    isn't covered by FILES (all problems at once, not just the first)."""
    targets = {(f, s): _Target(f, s) for f in FILES for s in f.sheets}
    by_territory = {_norm(t): tgt for tgt in targets.values() for t in tgt.sheet.territories}
    by_rep = {_norm(f.rep): f for f in FILES if f.rep}

    unknown_territories: dict[str, list[str]] = {}
    unknown_reps: dict[str, list[str]] = {}
    for order in orders:
        territory = order.first.get(TERRITORY)
        home = by_territory.get(_norm(territory))
        if home is None:
            unknown_territories.setdefault(str(territory), []).append(order.number)
            continue
        home.own.append(order)

        partner = order.first.get(SPLIT_WITH)
        if not _norm(partner):
            continue
        rep_file = by_rep.get(_norm(partner))
        if rep_file is None:
            unknown_reps.setdefault(str(partner), []).append(order.number)
            continue
        if rep_file is home.file:
            continue  # split with themselves: already in their file once
        state = str(order.first.get(SHIP_STATE) or "").strip().upper()
        sheet = next((s for s in rep_file.sheets if state in s.split_states), rep_file.sheets[0])
        targets[(rep_file, sheet)].split.append(order)

    if unknown_territories or unknown_reps:
        problems = [
            f"Sales Territory {t!r} ({len(n)} orders, e.g. {n[0]})" for t, n in unknown_territories.items()
        ] + [f"Split With {r!r} ({len(n)} orders, e.g. {n[0]})" for r, n in unknown_reps.items()]
        raise UnknownTerritory(
            "No rep file covers: " + "; ".join(problems)
            + ". Add it to app/reports/open_order/rep_files.py, then run again."
        )

    return [
        (
            f,
            [
                SheetSpec(s.name, by_number(targets[(f, s)].own), by_number(targets[(f, s)].split))
                for s in f.sheets
            ],
        )
        for f in FILES
    ]

