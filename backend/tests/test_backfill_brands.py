"""Filling `top_brands` on already-judged rows.

The property that matters: this is a MEASUREMENT, so it must never call the
model and never move a verdict. A backfill that re-judged would cost 35 minutes
and hand back a different set of answers.
"""
from types import SimpleNamespace

from app.prospects import backfill_brands as bf


class _DB:
    def __init__(self, rows): self.rows, self.commits = rows, 0
    def execute(self, q):
        rows = self.rows
        class _R:
            def scalars(self):
                class _S:
                    def all(_s): return rows
                return _S()
        return _R()
    def commit(self): self.commits += 1


def _row(**over):
    base = dict(store_name="X", website="https://x.com", top_brands=None,
                verdict="strong", assessed_at="2026-08-22")
    base.update(over)
    return SimpleNamespace(**base)


def test_the_shelf_is_written_deepest_first(monkeypatch):
    monkeypatch.setattr(bf.assess, "_scrape", lambda url: {"domain": "x.com",
        "products": [{"title": f"P{i}", "vendor": v} for i, v in
                     enumerate(["RAILS"] * 9 + ["VELVET"] * 4)], "about_text": ""})
    row = _row()
    assert bf.run(_DB([row])) == 1
    assert row.top_brands == "RAILS; VELVET"


def test_a_verdict_is_never_touched(monkeypatch):
    """The whole point: a measurement backfill must not re-decide anything."""
    monkeypatch.setattr(bf.assess, "_scrape", lambda url: {"domain": "x.com",
        "products": [{"title": "P", "vendor": "RAILS"}], "about_text": ""})
    row = _row(verdict="possible")
    bf.run(_DB([row]))
    assert row.verdict == "possible"


def test_a_shop_with_no_cached_pages_is_left_null_not_blank(monkeypatch):
    """NULL reads as 'not recorded'; '' would read as 'stocks no brands'."""
    def _boom(url): raise FileNotFoundError("nothing cached")
    monkeypatch.setattr(bf.assess, "_scrape", _boom)
    row = _row()
    assert bf.run(_DB([row])) == 0
    assert row.top_brands is None
