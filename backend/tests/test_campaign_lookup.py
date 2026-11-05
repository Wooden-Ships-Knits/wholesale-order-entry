"""Accept writes the order's campaign to Salesforce by looking up its name."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import admin
from app.salesforce import client, mapping


@pytest.mark.parametrize(
    "value, name",
    [
        ("rep-non-show", "Rep - Non Show Orders"),
        ("Other: 2026 Oct 12 - 14 LA Mart", "2026 Oct 12 - 14 LA Mart"),
        ("Other:    ", None),
        ("other", None),
        ("", None),
        (None, None),
    ],
)
def test_campaign_name_for(value, name):
    assert mapping.campaign_name_for(value) == name


def _capture_query(monkeypatch, rows):
    seen = []

    def fake(soql):
        seen.append(soql)
        return rows

    monkeypatch.setattr(client, "query_all", fake)
    return seen


def test_other_text_resolves_to_the_campaign_with_that_name(monkeypatch):
    seen = _capture_query(monkeypatch, [{"Id": "701LA"}])
    assert client.campaign_id_for("Other: 2026 Oct 12 - 14 LA Mart") == "701LA"
    assert "Name = '2026 Oct 12 - 14 LA Mart'" in seen[0]


def test_rep_non_show_resolves_by_its_fixed_name(monkeypatch):
    seen = _capture_query(monkeypatch, [{"Id": "701RN"}])
    assert client.campaign_id_for("rep-non-show") == "701RN"
    assert "Name = 'Rep - Non Show Orders'" in seen[0]


def test_typed_text_cannot_break_out_of_the_soql_literal(monkeypatch):
    seen = _capture_query(monkeypatch, [])
    client.campaign_id_for("Other: Macy's' OR Name != '")
    assert "Name = 'Macy\\'s\\' OR Name != \\''" in seen[0]


def test_no_match_returns_none(monkeypatch):
    _capture_query(monkeypatch, [])
    assert client.campaign_id_for("Other: Typo Show") is None


def test_no_campaign_named_skips_the_query(monkeypatch):
    seen = _capture_query(monkeypatch, [])
    assert client.campaign_id_for("other") is None
    assert client.campaign_id_for("") is None
    assert seen == []


def _order(campaign):
    return SimpleNamespace(
        id="abc12345-order",
        sf_order_id=None,
        sf_order_number=None,
        sf_account_id="001X",
        sf_account_created_at="already-created",
        account_name="A Pied",
        season_code="F26",
        campaign=campaign,
        sales_territory=None,
    )


@pytest.fixture
def push(monkeypatch):
    """Everything around the campaign in the push, stubbed. Yields the header
    build's campaign_id argument list and the create call's success."""
    captured = {}

    def build(order, pricebook_id, sales_territory=None, campaign_id=None):
        captured["campaign_id"] = campaign_id
        return {}

    monkeypatch.setattr(client, "get_wholesale_pricebook_id", lambda s: "01s")
    monkeypatch.setattr(client, "match_order_territory", lambda t: None)
    monkeypatch.setattr(client, "create_sales_order", lambda h, l: ("a0X", "SO-1"))
    monkeypatch.setattr(mapping, "build_sales_order_lines", lambda o: [{"line": 1}])
    monkeypatch.setattr(mapping, "build_sales_order_header", build)
    return captured


def test_push_sends_the_matched_campaign_without_a_warning(monkeypatch, push):
    monkeypatch.setattr(client, "campaign_id_for", lambda v: "701LA")
    order = _order("Other: 2026 Oct 12 - 14 LA Mart")
    assert admin._push_order_to_salesforce(order) is None
    assert push["campaign_id"] == "701LA"
    assert order.sf_order_number == "SO-1"


def test_push_still_creates_the_order_and_warns_on_no_match(monkeypatch, push):
    monkeypatch.setattr(client, "campaign_id_for", lambda v: None)
    order = _order("Other: Typo Show")
    warning = admin._push_order_to_salesforce(order)
    assert order.sf_order_id == "a0X"
    assert push["campaign_id"] is None
    assert '"Typo Show"' in warning and "SO-1" in warning


@pytest.mark.parametrize("campaign", ["", None, "other"])
def test_push_does_not_warn_when_no_campaign_was_named(monkeypatch, push, campaign):
    monkeypatch.setattr(client, "campaign_id_for", lambda v: None)
    assert admin._push_order_to_salesforce(_order(campaign)) is None


def test_push_failure_still_raises(monkeypatch, push):
    monkeypatch.setattr(client, "campaign_id_for", lambda v: "701LA")

    def boom(h, l):
        raise RuntimeError("rejected")

    monkeypatch.setattr(client, "create_sales_order", boom)
    with pytest.raises(HTTPException):
        admin._push_order_to_salesforce(_order("Other: X"))
