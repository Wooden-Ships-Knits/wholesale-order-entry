"""The buyer-lookup SOQL asks for what map_account() needs.

The mapping helpers read ContactBuying__r and the Contacts child subquery, so
if the query stops selecting them the autofill and the rep picker silently go
empty for every account. That failure is invisible in a mapping unit test,
hence this one.
"""
from unittest.mock import patch

from app.salesforce import client


def _run_lookup(**kwargs):
    """Capture the SOQL find_accounts() builds, without touching Salesforce."""
    with patch.object(client, "query_all", return_value=[]) as q:
        client.find_accounts(**kwargs)
    return q.call_args[0][0]


def test_query_selects_the_buying_contact_name():
    assert "ContactBuying__r.Name" in _run_lookup(email="buyer@apied.com")


def test_query_selects_the_buying_contact_title():
    assert "ContactBuying__r.Title" in _run_lookup(email="buyer@apied.com")


def test_query_includes_the_related_contacts_subquery():
    assert "(SELECT Name, Title FROM Contacts ORDER BY Name)" in _run_lookup(email="buyer@apied.com")


def test_subquery_sits_inside_the_select_clause():
    """A child subquery is only legal between SELECT and FROM."""
    soql = _run_lookup(name="A PIED")
    assert soql.index("(SELECT Name, Title FROM Contacts ORDER BY Name)") < soql.index(" FROM Account")


def test_admin_lookup_gets_the_same_fields():
    """The admin account picker uses include_excluded=True and must not lose
    the buyer name."""
    soql = _run_lookup(account_id="0012v00000AbCdEAAV", include_excluded=True)
    assert "ContactBuying__r.Name" in soql
    assert "(SELECT Name, Title FROM Contacts ORDER BY Name)" in soql
