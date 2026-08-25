"""Reading a shop's shelf back out of the cache.

`top_brands` is computed at assessment time and never stored, so the gate that
turns on it cannot be audited from the table. This is how you look.
"""
from app.prospects import inspect


def _store(vendors):
    return {"products": [{"title": f"P{i}", "vendor": v} for i, v in enumerate(vendors)]}


def test_the_shelf_is_ordered_by_how_deeply_each_brand_is_stocked():
    got = inspect.shelf(_store(["RAILS"] * 3 + ["VELVET"] * 5 + ["FRAME"]))
    assert [b for b, _ in got.most_common()] == ["VELVET", "RAILS", "FRAME"]


def test_blank_vendors_are_not_a_brand_called_nothing():
    """A product with no vendor is an unrecorded brand, not an unnamed one —
    counting it would inflate brand_count with the shop's own gaps."""
    assert inspect.shelf(_store(["RAILS", "", "  ", None])) == {"RAILS": 1}


def test_vendor_strings_are_matched_case_and_space_insensitively():
    """The same brand typed three ways is one brand — this is what makes a
    self-named shelf visible as 946 of 967 rather than three tidy entries."""
    got = inspect.shelf(_store([" rails ", "RAILS", "Rails"]))
    assert got == {"RAILS": 3}
