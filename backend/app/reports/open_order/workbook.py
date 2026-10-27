"""The OO workbook: one sheet laid out like the team's "Master - OO" file.

One row per order line, in Sales Territory order (the report's grouping) then
order number; an "<order> Total" row after each order; a Grand Total at the
bottom. Every row of an order — lines and its total — carries the order's
colour:

    YELLOW  entered in the last 7 days — make sure nothing is missing
    ORANGE  within its ship window — check the Problem List in case it is stuck
    RED     past its ship window — see the Problem List Email

An order matching more than one takes the most urgent: red, then orange, then
yellow. A brand-new order whose window is already open needs chasing, not just
checking.

Grouped like Excel's Subtotal outline, as the team's file is: an order's lines
are level 2 and start hidden, its Total row is level 1 — so the file opens as
one row per order, and the − / + buttons below each order open its lines. The
Total row carries the order's own details (territory, dates, account, …) so
the collapsed view says what each order is; product columns stay blank there.

Deliberately NOT copied from the hand-made file: its descriptive columns sat one
row lower than the quantities (each order's first line blank, its Total row
repeating the last line's product). Here every line carries its own product.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import xlsxwriter

# (Salesforce detail column, header in the team's file, kind, width)
COLUMNS = [
    # The order's own territory (the report's grouping — see fetch.SALES_TERRITORY),
    # not the report's "Current Sales Territory" column.
    ("kugo2p__SalesOrder__c.kugo2p__SalesTerritory__c", "Sales Territory", "text", 16),
    ("CUST_NAME", "Order: Order Number", "text", 18),
    ("kugo2p__SalesOrder__c.kugo2p__OrderDate__c", "Order Date", "date", 10),
    ("kugo2p__SalesOrder__c.Start_Ship_Date__c", "Start Ship Date", "date", 10),
    ("kugo2p__SalesOrder__c.Ship_Thru__c", "Ship Thru Date", "date", 10),
    ("kugo2p__SalesOrder__c.Type__c", "Type", "text", 17),
    ("kugo2p__SalesOrder__c.kugo2p__Account__c", "Account Name", "text", 25),
    ("kugo2p__SalesOrder__c.kugo2p__ShipToStateProvince__c", "Ship To State/Province", "text", 6),
    ("kugo2p__SalesOrder__c.kugo2p__CustomerPONumber__c", "Customer PO Number", "text", 9),
    ("kugo2p__SalesOrder__c.Campaign__c", "Campaign", "text", 16),
    ("kugo2p__SalesOrderProductLine__c.kugo2p__ProductFamily__c", "Product Family", "text", 15),
    ("kugo2p__SalesOrderProductLine__c.Product_Code__c", "Product Code", "text", 14),
    ("FK_NAME", "Product: Product Name", "text", 43),
    ("kugo2p__SalesOrderProductLine__c.kugo2p__Quantity__c", "Quantity", "qty", 6),
    ("kugo2p__SalesOrderProductLine__c.kugo2p__SalesPrice__c", "Sales Price", "money", 8),
    ("kugo2p__SalesOrderProductLine__c.kugo2p__TotalAmount__c", "Total Amount", "money", 10),
    ("kugo2p__SalesOrder__c.Split_Commission__c", "Split Commission", "text", 8),
    ("kugo2p__SalesOrder__c.Split_With__c", "Split With", "text", 9),
]
ORDER_NO = "CUST_NAME"
ORDER_DATE = "kugo2p__SalesOrder__c.kugo2p__OrderDate__c"
START = "kugo2p__SalesOrder__c.Start_Ship_Date__c"
THRU = "kugo2p__SalesOrder__c.Ship_Thru__c"
TERRITORY = "kugo2p__SalesOrder__c.kugo2p__SalesTerritory__c"
ACCOUNT = "kugo2p__SalesOrder__c.kugo2p__Account__c"
QTY = "kugo2p__SalesOrderProductLine__c.kugo2p__Quantity__c"
AMOUNT = "kugo2p__SalesOrderProductLine__c.kugo2p__TotalAmount__c"

# Columns that describe the ORDER, not a line — repeated on its Total row so the
# collapsed outline reads as a list of orders.
ORDER_LEVEL = {
    TERRITORY,
    ORDER_DATE,
    START,
    THRU,
    "kugo2p__SalesOrder__c.Type__c",
    ACCOUNT,
    "kugo2p__SalesOrder__c.kugo2p__ShipToStateProvince__c",
    "kugo2p__SalesOrder__c.kugo2p__CustomerPONumber__c",
    "kugo2p__SalesOrder__c.Campaign__c",
    "kugo2p__SalesOrder__c.Split_Commission__c",
    "kugo2p__SalesOrder__c.Split_With__c",
}

# The fills the team's file uses (yellow, orange) plus red.
FILLS = {"yellow": "#FFFF00", "orange": "#FF9900", "red": "#FF0000"}
LAST_WEEK_DAYS = 7


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def order_colour(order_date: Any, start: Any, thru: Any, today: date) -> str | None:
    """'red' | 'orange' | 'yellow' | None for one order (see module docstring)."""
    od, s, t = _date(order_date), _date(start), _date(thru)
    if t and today > t:
        return "red"
    if s and t and s <= today <= t:
        return "orange"
    if od and od >= today - timedelta(days=LAST_WEEK_DAYS):
        return "yellow"
    return None


@dataclass
class Order:
    number: str
    lines: list[dict[str, Any]]
    colour: str | None
    qty: float = 0
    amount: float = 0
    first: dict[str, Any] = field(default_factory=dict)


def group_orders(rows: list[dict[str, Any]], today: date) -> list[Order]:
    """Lines → orders, sorted alphabetically by the Sales Territory shown in
    column A (orders with none last), then order number. Lines keep the order
    the report returned them in.

    Not the report's own grouping order: Salesforce sorts the territory picklist
    in its configured order ("Southeast" above "South"), while the team's file
    is alphabetical."""
    by_number: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_number.setdefault(str(row.get(ORDER_NO) or ""), []).append(row)

    orders = []
    for number, lines in by_number.items():
        first = lines[0]
        orders.append(
            Order(
                number=number,
                lines=lines,
                colour=order_colour(first.get(ORDER_DATE), first.get(START), first.get(THRU), today),
                qty=sum(float(r.get(QTY) or 0) for r in lines),
                amount=sum(float(r.get(AMOUNT) or 0) for r in lines),
                first=first,
            )
        )
    def territory_key(o: Order) -> tuple:
        territory = str(o.first.get(TERRITORY) or "").strip()
        return (territory == "", territory.casefold(), o.number)

    orders.sort(key=territory_key)
    return orders


def by_number(orders: list[Order]) -> list[Order]:
    """Oldest order number first — how the rep files are sorted."""
    return sorted(orders, key=lambda o: o.number)


@dataclass
class SheetSpec:
    name: str
    own: list[Order]
    # Orders split with this sheet's rep from another territory. Written as a
    # section of their own below the rep's orders, with subtotals.
    split: list[Order] = field(default_factory=list)


class _Book:
    """One .xlsx being written: its formats, and the sheet layout every OO
    file shares (header, coloured collapsed orders, totals)."""

    def __init__(self) -> None:
        self.buf = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True})
        self._formats: dict[tuple, Any] = {}

    def fmt(self, kind: str = "text", colour: str | None = None, bold: bool = False):
        key = (kind, colour, bold)
        if key not in self._formats:
            props: dict[str, Any] = {"bold": bold}
            if colour:
                props.update(bg_color=FILLS[colour], pattern=1)
            if kind == "date":
                props["num_format"] = "m/d/yy"
            elif kind == "money":
                props["num_format"] = '"$"#,##0'
            self._formats[key] = self.wb.add_format(props)
        return self._formats[key]

    def sheet(self, spec: SheetSpec) -> None:
        ws = self.wb.add_worksheet(spec.name)
        # Outline buttons below each group (the Total row is the summary row).
        ws.outline_settings(True, True, True, False)
        header = self.fmt("text", "yellow", bold=True)
        for c, (_, title, _, width) in enumerate(COLUMNS):
            ws.write_string(0, c, title, header)
            ws.set_column(c, c, width)
        ws.freeze_panes(1, 0)

        def put(r: int, c: int, kind: str, value: Any, f) -> None:
            if value is None or value == "":
                ws.write_blank(r, c, None, f)
            elif kind == "date" and _date(value):
                ws.write_datetime(r, c, datetime.combine(_date(value), datetime.min.time()), f)
            elif kind in ("qty", "money"):
                ws.write_number(r, c, float(value), f)
            else:
                ws.write_string(r, c, str(value), f)

        def summary(r: int, label: str, qty: float, amount: float) -> None:
            for c, (col, _, kind, _) in enumerate(COLUMNS):
                if col == ORDER_NO:
                    ws.write_string(r, c, label, self.fmt("text", bold=True))
                elif col == QTY:
                    ws.write_number(r, c, qty, self.fmt("qty", bold=True))
                elif col == AMOUNT:
                    ws.write_number(r, c, amount, self.fmt("money", bold=True))

        def orders(r: int, rows: list[Order]) -> int:
            for order in rows:
                for line in order.lines:
                    for c, (col, _, kind, _) in enumerate(COLUMNS):
                        put(r, c, kind, line.get(col), self.fmt(kind, order.colour))
                    ws.set_row(r, None, None, {"level": 2, "hidden": True})
                    r += 1
                for c, (col, _, kind, _) in enumerate(COLUMNS):
                    f = self.fmt(kind, order.colour, bold=True)
                    if col == ORDER_NO:
                        ws.write_string(r, c, f"{order.number} Total", f)
                    elif col == QTY:
                        ws.write_number(r, c, order.qty, f)
                    elif col == AMOUNT:
                        ws.write_number(r, c, order.amount, f)
                    elif col in ORDER_LEVEL:
                        put(r, c, kind, order.first.get(col), f)
                    else:
                        ws.write_blank(r, c, None, f)
                # "collapsed" goes on the row after the hidden group — its Total.
                ws.set_row(r, None, None, {"level": 1, "collapsed": True})
                r += 1
            return r

        def totals(rows: list[Order]) -> tuple[float, float]:
            return sum(o.qty for o in rows), sum(o.amount for o in rows)

        r = orders(1, spec.own)
        if spec.split:
            ws.write_string(r, 1, "Split orders", self.fmt("text", bold=True))
            r = orders(r + 1, spec.split)
            summary(r, "Own orders total", *totals(spec.own))
            summary(r + 1, "Split orders total", *totals(spec.split))
            r += 2
        # Grand Total = everything on the sheet, split copies included — as the
        # team's rep files total it.
        summary(r, "Grand Total", *totals(spec.own + spec.split))

    def close(self) -> bytes:
        self.wb.close()
        return self.buf.getvalue()


def build_book(sheets: list[SheetSpec]) -> bytes:
    """An .xlsx with one sheet per spec, as bytes."""
    book = _Book()
    for spec in sheets:
        book.sheet(spec)
    return book.close()


def build(orders: list[Order]) -> bytes:
    """The Master file: every order on one sheet, in territory order."""
    return build_book([SheetSpec("Master", orders)])
