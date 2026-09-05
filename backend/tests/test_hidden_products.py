"""Hiding a style+color from the order form.

The property worth pinning is not "the flag is set" but "the row is still
there". Dropping hidden rows from /api/products would break the signing page,
which rebuilds a saved draft's lines by matching style+color against this same
catalogue — so the test asserts the row count is unchanged, which is the thing
a future refactor is tempted to get wrong. No database needed: flag_rows is
pure, and the DB side is two statements keyed by the primary key.
"""
from app.services.hidden_products import flag_rows


def rows():
    return [
        {"code": "K57", "styleName": "ASPEN", "color": "OATMEAL", "unitPrice": 132.0},
        {"code": "K57", "styleName": "ASPEN", "color": "CHARCOAL", "unitPrice": 132.0},
        {"code": "K57", "styleName": "BOWERY", "color": "OATMEAL", "unitPrice": 148.0},
    ]


def test_hidden_rows_are_flagged_not_removed():
    out = flag_rows(rows(), {("ASPEN", "CHARCOAL")})
    assert len(out) == 3, "a hidden row must survive — SignPage resolves drafts against it"
    assert [r["hidden"] for r in out] == [False, True, False]


def test_a_color_is_hidden_without_taking_its_style_with_it():
    out = flag_rows(rows(), {("ASPEN", "CHARCOAL")})
    aspen = [r for r in out if r["styleName"] == "ASPEN"]
    assert [r["color"] for r in aspen if not r["hidden"]] == ["OATMEAL"]


def test_the_same_color_under_another_style_is_untouched():
    """The key is the pair. Hiding ASPEN/OATMEAL must not hide BOWERY/OATMEAL."""
    out = flag_rows(rows(), {("ASPEN", "OATMEAL")})
    assert next(r for r in out if r["styleName"] == "BOWERY")["hidden"] is False


def test_every_row_carries_the_flag_when_nothing_is_hidden():
    """The frontend reads r.hidden directly — an absent key would be a silent
    'visible' today and a crash the day someone writes r.hidden.toString()."""
    assert all(r["hidden"] is False for r in flag_rows(rows(), set()))
