"""Ship-window start date for the /admin "window already opened" flag."""
from app.salesforce import mapping


def test_start_uses_the_sheet_year(monkeypatch):
    # Spring 27 ships from December 2026 — the sheet's Year row says so.
    monkeypatch.setattr(mapping, "_window_year", lambda w, s: 2026)
    assert mapping.ship_window_start("12/1-30", "S27") == "2026-12-01"


def test_start_falls_back_to_the_month_rule(monkeypatch):
    monkeypatch.setattr(mapping, "_window_year", lambda w, s: None)
    assert mapping.ship_window_start("12/1-30", "S27") == "2026-12-01"
    assert mapping.ship_window_start("8/1-31", "F26") == "2026-08-01"


def test_start_none_when_unparseable(monkeypatch):
    monkeypatch.setattr(mapping, "_window_year", lambda w, s: None)
    assert mapping.ship_window_start(None, "F26") is None
    assert mapping.ship_window_start("", "F26") is None
    assert mapping.ship_window_start("sometime soon", "F26") is None
