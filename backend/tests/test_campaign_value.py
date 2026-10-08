"""Stored campaign value — shared by order submit and the /admin campaign edit."""
from app.routers.orders import campaign_value


def test_rep_non_show_stored_as_is():
    assert campaign_value("rep-non-show") == "rep-non-show"


def test_other_carries_its_text():
    assert campaign_value("other", "  Atlanta show ") == "Other: Atlanta show"


def test_other_without_text_stays_bare():
    assert campaign_value("other", "   ") == "other"


def test_empty_stays_empty():
    assert campaign_value("") == ""
