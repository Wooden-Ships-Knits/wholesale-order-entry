"""OO (Open Order) report — colour rules, grouping and the workbook."""
import io
import zipfile
from datetime import date

from app.reports.open_order import workbook as wb
from app.reports.open_order.fetch import _cell

TODAY = date(2026, 10, 26)


# ------------------------------------------------------------- order colour
def test_entered_in_the_last_week_is_yellow():
    assert wb.order_colour("2026-10-20", "2027-02-01", "2027-02-28", TODAY) == "yellow"
    assert wb.order_colour("2026-10-19", "2027-02-01", "2027-02-28", TODAY) == "yellow"  # 7 days ago


def test_older_than_a_week_is_not_yellow():
    assert wb.order_colour("2026-10-18", "2027-02-01", "2027-02-28", TODAY) is None


def test_within_the_ship_window_is_orange():
    assert wb.order_colour("2026-08-01", "2026-10-01", "2026-10-31", TODAY) == "orange"
    assert wb.order_colour("2026-08-01", "2026-10-26", "2026-10-31", TODAY) == "orange"  # opens today
    assert wb.order_colour("2026-08-01", "2026-10-01", "2026-10-26", TODAY) == "orange"  # closes today


def test_past_the_ship_window_is_red():
    assert wb.order_colour("2026-08-01", "2026-09-01", "2026-10-25", TODAY) == "red"


def test_most_urgent_colour_wins():
    # Entered this week AND already inside its window: chase it, don't just check it.
    assert wb.order_colour("2026-10-24", "2026-10-01", "2026-10-31", TODAY) == "orange"
    assert wb.order_colour("2026-10-24", "2026-09-01", "2026-10-01", TODAY) == "red"


def test_missing_dates_do_not_crash():
    assert wb.order_colour(None, None, None, TODAY) is None
    assert wb.order_colour("2026-10-25", None, None, TODAY) == "yellow"


# ------------------------------------------------------------- grouping
def _line(order, territory, qty, amount, product="P", order_date="2026-06-11"):
    return {
        wb.TERRITORY: territory,
        wb.ORDER_NO: order,
        wb.ORDER_DATE: order_date,
        wb.START: "2027-02-01",
        wb.THRU: "2027-02-28",
        wb.QTY: qty,
        wb.AMOUNT: amount,
        "FK_NAME": product,
    }


def test_orders_sorted_by_territory_then_number_with_totals():
    rows = [
        _line("SO-3", "South - Vickie Wilde", 2, 100),
        _line("SO-2", "Southeast - Jason Hilsenrad", 6, 420, product="B"),
        _line("SO-9", None, 1, 50),  # no territory: last
        _line("SO-1", "South - Vickie Wilde", 4, 200),
        _line("SO-2", "Southeast - Jason Hilsenrad", 2, 140, product="A"),
    ]
    orders = wb.group_orders(rows, TODAY)
    assert [o.number for o in orders] == ["SO-1", "SO-3", "SO-2", "SO-9"]
    orders = [o for o in orders if o.number == "SO-2"]
    assert orders[0].qty == 8 and orders[0].amount == 560
    # Lines keep the report's own order within an order.
    assert [line["FK_NAME"] for line in orders[0].lines] == ["B", "A"]


# ------------------------------------------------------------- workbook
def test_build_writes_lines_totals_and_fills():
    rows = [
        _line("SO-1", "A", 2, 140, order_date="2026-10-25"),  # yellow
        _line("SO-1", "A", 6, 420, order_date="2026-10-25"),
        _line("SO-2", "A", 4, 200),  # no colour
    ]
    data = wb.build(wb.group_orders(rows, TODAY))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        strings = z.read("xl/sharedStrings.xml").decode()
        styles = z.read("xl/styles.xml").decode()
    assert "SO-1 Total" in strings and "SO-2 Total" in strings and "Grand Total" in strings
    assert "Order: Order Number" in strings
    # header + 3 lines + 2 order totals + grand total
    assert sheet.count("<row ") == 7
    assert "FFFFFF00" in styles  # yellow fill (header and SO-1)


# ------------------------------------------------------------- report cells
def test_cell_values():
    assert _cell({"value": None, "label": "-"}) is None
    assert _cell({"value": {"amount": 70.0, "currency": "USD"}, "label": "$70.00"}) == 70.0
    assert _cell({"value": 6.0, "label": "6.0000"}) == 6.0
    assert _cell({"value": "001xx0000000001", "label": "MISS MEER'S (EUGENE)"}) == "MISS MEER'S (EUGENE)"
    # Dates keep the ISO value, not the display label, or the colours can't be worked out.
    assert _cell({"value": "2026-06-11", "label": "6/11/2026"}, "date") == "2026-06-11"


def test_build_groups_lines_under_collapsed_order_totals():
    rows = [
        _line("SO-1", "A", 2, 140),
        _line("SO-1", "A", 6, 420),
    ]
    rows[0][wb.ACCOUNT] = rows[1][wb.ACCOUNT] = "MISS MEER'S (EUGENE)"
    data = wb.build(wb.group_orders(rows, TODAY))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
        strings = z.read("xl/sharedStrings.xml").decode()
    # Two hidden level-2 lines, then the order's Total at level 1, collapsed.
    assert sheet.count('outlineLevel="2"') == 2
    assert sheet.count('hidden="1"') == 2
    assert 'outlineLevel="1" collapsed="1"' in sheet
    # Buttons below each group: Excel's default, so it must not be switched off.
    assert 'summaryBelow="0"' not in sheet
    # The Total row repeats the account so the collapsed view names the order.
    assert "MISS MEER" in strings


# ------------------------------------------------------------- rep files
from app.reports.open_order import rep_files as rf  # noqa: E402


def _order(number, territory, split_with=None, state="CA", amount=100):
    line = _line(number, territory, 2, amount)
    line[rf.SPLIT_WITH] = split_with
    line[rf.SHIP_STATE] = state
    return wb.group_orders([line], TODAY)[0]


def _sheets(books):
    """{sheet name: ([own numbers], [split numbers])} across every file."""
    return {s.name: ([o.number for o in s.own], [o.number for o in s.split]) for _, sheets in books for s in sheets}


def test_each_territory_lands_on_its_reps_sheet():
    books = rf.split_orders([
        _order("SO-2", "CA/HI - Rande Cohen"),
        _order("SO-1", "CA/HI - Rande Cohen"),
        _order("SO-3", "Long Island - Kitty Tally", state="NY"),
        _order("SO-4", "Upstate NY - Kitty Tally", state="NY"),
        _order("SO-5", "FL - Jason Hilsenrad", state="FL"),
        _order("SO-6", "Pacific Northwest - House", state="OR"),
        _order("SO-7", None),  # no territory -> House
    ])
    sheets = _sheets(books)
    assert sheets["CA, HI - Rande Cohen"] == (["SO-1", "SO-2"], [])  # sorted by order number
    assert sheets["NY - Kitty Tally"] == (["SO-3", "SO-4"], [])
    assert sheets["FL - Jason Hilsenrad"] == (["SO-5"], [])
    assert sheets["House"] == (["SO-6", "SO-7"], [])


def test_split_copy_goes_to_the_partner_and_stays_home():
    books = rf.split_orders([
        _order("SO-1", "Pacific Northwest - House", split_with="Rande Cohen", state="OR"),
        _order("SO-2", "Midwest - Aviva Landin", split_with="Vickie Wilde", state="IL"),
    ])
    sheets = _sheets(books)
    assert sheets["House"] == (["SO-1"], [])
    assert sheets["CA, HI - Rande Cohen"] == ([], ["SO-1"])
    assert sheets["Midwest - Aviva Landin"] == (["SO-2"], [])
    assert sheets["South - Vickie Wilde"] == ([], ["SO-2"])


def test_split_with_yourself_is_not_copied():
    sheets = _sheets(rf.split_orders([_order("SO-1", "CA/HI - Rande Cohen", split_with="Rande Cohen")]))
    assert sheets["CA, HI - Rande Cohen"] == (["SO-1"], [])


def test_split_copy_uses_the_ship_to_state_sheet():
    sheets = _sheets(rf.split_orders([
        _order("SO-1", "Mid Atlantic - Michael Young", split_with="Jason Hilsenrad", state="VA"),
        _order("SO-2", "Mid Atlantic - Michael Young", split_with="Jason Hilsenrad", state="FL"),
        _order("SO-3", "Upstate NY - Amanda Santoro", split_with="Kitty Tally", state="NY"),
        _order("SO-4", "Mid Atlantic - Michael Young", split_with="Kitty Tally", state="CT"),
    ]))
    assert sheets["Southeast - Jason Hilsenrad"][1] == ["SO-1"]
    assert sheets["FL - Jason Hilsenrad"][1] == ["SO-2"]
    assert sheets["NY - Kitty Tally"][1] == ["SO-3"]
    assert sheets["New England - Kitty Tally"][1] == ["SO-4"]


def test_unknown_territory_or_rep_stops_the_run():
    import pytest

    with pytest.raises(rf.UnknownTerritory) as err:
        rf.split_orders([
            _order("SO-1", "Texas - New Rep"),
            _order("SO-2", "CA/HI - Rande Cohen", split_with="Someone New"),
        ])
    assert "Texas - New Rep" in str(err.value) and "Someone New" in str(err.value)


def test_every_order_is_filed_once_plus_its_split_copies():
    orders = [
        _order(f"SO-{i}", t, split_with=sw)
        for i, (t, sw) in enumerate([
            ("CA/HI - Rande Cohen", None),
            ("Southeast - Jason Hilsenrad", "Vickie Wilde"),
            ("NM/MT - House", "Rande Cohen"),
        ])
    ]
    books = rf.split_orders(orders)
    own = [o.number for _, sheets in books for s in sheets for o in s.own]
    split = [o.number for _, sheets in books for s in sheets for o in s.split]
    assert sorted(own) == sorted(o.number for o in orders)
    assert sorted(split) == ["SO-1", "SO-2"]


def test_rep_file_names():
    day = date(2026, 10, 27)
    names = {f.filename(day) for f in rf.FILES}
    assert "OO-CA,HI-YTD-261027-Rande.xlsx" in names
    assert "OO-Southeast, FL-YTD-261027-Jason.xlsx" in names
    assert "OO-House-YTD-261027.xlsx" in names
    assert len(names) == 9
    # Excel's sheet-name rules.
    for f in rf.FILES:
        for s in f.sheets:
            assert len(s.name) <= 31 and not set(s.name) & set("/\\?*[]:")


def test_rep_sheet_has_split_section_and_subtotals():
    own = wb.group_orders([_line("SO-1", "CA/HI - Rande Cohen", 2, 140)], TODAY)
    split = wb.group_orders([_line("SO-2", "Pacific Northwest - House", 4, 300)], TODAY)
    data = wb.build_book([wb.SheetSpec("CA, HI - Rande Cohen", own, split)])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        strings = z.read("xl/sharedStrings.xml").decode()
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    for label in ("Split orders", "Own orders total", "Split orders total", "Grand Total"):
        assert label in strings
    assert "<v>440</v>" in sheet  # Grand Total = own 140 + split 300
