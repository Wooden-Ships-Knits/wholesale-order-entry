"""Reading a shop's shelf back out of the cache.

`top_brands` is computed at assessment time and never stored, so the gate that
turns on it cannot be audited from the table. This is how you look.
"""
from types import SimpleNamespace

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


# --- the goods themselves ---------------------------------------------------
# The shelf answers "whose brands", which is what the house-brand gate turns
# on. It does not answer "what does this shop actually sell", and that is the
# question a person asks when they doubt a verdict: Phoebe Jon reads as a
# 10-brand boutique until you see that 114 of its 124 products carry its own
# name and the other nine brands are gloves, belts and scarves.

def _priced(rows):
    return {"products": [{"title": t, "vendor": v, "price": p} for t, v, p in rows]}


def test_goods_can_be_narrowed_to_one_brand_however_it_was_typed():
    store = _priced([("Cardigan", "PHOEBE JON", 210), ("Gloves", "PORTOLANO", 80)])
    got = inspect.goods(store, brand="phoebe jon")
    assert [g["title"] for g in got] == ["Cardigan"]


def test_goods_marks_which_items_are_knitwear():
    """The price band argument is about knitwear, not about the whole shop —
    so a row you are checking has to show which items the rule even counted."""
    store = _priced([("Cashmere Sweater", "X", 200), ("Leather Belt", "X", 90)])
    got = {g["title"]: g["knit"] for g in inspect.goods(store)}
    assert got == {"Cashmere Sweater": True, "Leather Belt": False}


def test_goods_are_ordered_by_price_with_unpriced_last():
    """Sorted by price because the question being asked is almost always
    'does this shop sell where we sell', which a price-ordered list answers
    at a glance. An unpriced item is unknown, not free — it sorts last."""
    store = _priced([("Mid", "X", 150), ("None", "X", None), ("Top", "X", 400)])
    assert [g["title"] for g in inspect.goods(store)] == ["Top", "Mid", "None"]


def test_goods_with_no_brand_filter_returns_the_whole_catalogue():
    store = _priced([("A", "X", 10), ("B", "Y", 20)])
    assert len(inspect.goods(store)) == 2


def test_report_lists_the_brand_it_was_asked_for(monkeypatch):
    """A loop variable outlives its loop in Python, and the shelf listing once
    looped over `brand` -- the same name as this function's argument. That
    rebound the caller's choice to the last brand printed, so asking for
    PHOEBE JON silently listed J SOCIETY: the wrong shop's goods under the
    right shop's heading, on the one tool used to doubt a verdict."""
    store = {"products": [{"title": "Cardigan", "vendor": "PHOEBE JON", "price": 210},
                          {"title": "Gloves", "vendor": "J SOCIETY", "price": 80}],
             "domain": "thephoebejon.com", "about_text": ""}
    row = SimpleNamespace(store_name="Phoebe Jon", website="thephoebejon.com",
                          verdict="strong")

    monkeypatch.setattr(inspect.assess, "load_pattern", lambda: {})
    monkeypatch.setattr(inspect.assess, "tag_signature", lambda p: {})
    monkeypatch.setattr(inspect.assess, "_scrape", lambda w: store)
    monkeypatch.setattr(inspect, "store_payload", lambda *a, **k: {
        "catalogue_size": 2, "brand_count": 2, "products_per_brand": 1.0})
    monkeypatch.setattr(inspect, "unreadable_reason", lambda *a, **k: None)

    seen = {}
    real = inspect.goods
    monkeypatch.setattr(inspect, "goods",
                        lambda s, brand=None: seen.setdefault("brand", brand) and None
                        or real(s, brand=brand))

    class _DB:
        def execute(self, *a, **k):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: row))

    inspect.report(_DB(), name="Phoebe Jon", brand="PHOEBE JON")
    assert seen["brand"] == "PHOEBE JON"
