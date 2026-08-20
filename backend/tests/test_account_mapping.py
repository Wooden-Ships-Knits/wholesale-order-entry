"""Buyer-name resolution from the Salesforce buying contact.

Coverage is on the rule itself: which contact becomes Bill To "Buyer name",
and — just as important — when we refuse to guess and leave it blank.
"""
from app.salesforce.mapping import _buyer_name


def _account(buying=None, buying_title=None, contacts=None):
    """Minimal Account record in the shape SOQL actually returns.

    ContactBuying__r is a parent traversal (nested dict or None); Contacts is
    a child subquery ({"records": [...]} or None when there are none).
    """
    return {
        "Id": "0012v00000AbCdEAAV",
        "Name": "A PIED",
        "ContactBuying__r": (
            {"Name": buying, "Title": buying_title} if buying is not None else None
        ),
        "Contacts": {"records": contacts} if contacts is not None else None,
    }


def _contact(name, title=None):
    return {"Name": name, "Title": title}


def test_uses_the_designated_buying_contact():
    assert _buyer_name(_account(buying="Kathleen Belavitch")) == "Kathleen Belavitch"


def test_buying_contact_wins_over_related_contacts():
    rec = _account(buying="Kathleen Belavitch", contacts=[_contact("Someone Else")])
    assert _buyer_name(rec) == "Kathleen Belavitch"


def test_falls_back_to_a_sole_related_contact():
    assert _buyer_name(_account(contacts=[_contact("Emily Egan")])) == "Emily Egan"


def test_falls_back_to_the_only_contact_titled_buyer():
    # FLEA (BROOKLYN) in the real org: three contacts, one titled "Buyer".
    rec = _account(contacts=[
        _contact("Pierre Pujos"),
        _contact("Jennifer Szymchack"),
        _contact("Ines Pujos", "Buyer"),
    ])
    assert _buyer_name(rec) == "Ines Pujos"


def test_buyer_title_match_ignores_case_and_surrounding_text():
    rec = _account(contacts=[
        _contact("Lisa Merritt", "BUYER apparel/hats"),
        _contact("Rob Skinner", "AP manager"),
    ])
    assert _buyer_name(rec) == "Lisa Merritt"


def test_ignores_a_buyer_who_no_longer_works_there():
    # A title can say "buyer" and "gone" at once. QVC's two contacts are both
    # ex-staff, so there is nobody left to name.
    rec = _account(contacts=[
        _contact("Amy Corey", "buyer - no longer there"),
        _contact("Mary Kate Mehl", "assistant"),
    ])
    assert _buyer_name(rec) is None


def test_a_current_buyer_still_wins_when_a_former_one_is_present():
    # Both titled buyer; only one of them still works there.
    rec = _account(contacts=[
        _contact("Sarah Burton", "Buyer - no longer"),
        _contact("Stefania Squitieri", "Buyer"),
    ])
    assert _buyer_name(rec) == "Stefania Squitieri"


def test_returns_none_when_two_contacts_are_both_titled_buyer():
    # THE BEAD EXPERIENCE: two contacts, both "_BUYER". No way to choose.
    rec = _account(contacts=[
        _contact("Idy", "_BUYER"),
        _contact("Julie Harris", "_BUYER"),
    ])
    assert _buyer_name(rec) is None


def test_returns_none_when_several_contacts_have_no_distinguishing_title():
    rec = _account(contacts=[_contact("Katie"), _contact("Laura")])
    assert _buyer_name(rec) is None


def test_returns_none_when_there_are_no_contacts_at_all():
    assert _buyer_name(_account()) is None


def test_ignores_contacts_with_a_blank_name():
    rec = _account(contacts=[_contact("   "), _contact("Heidi Jorgensen")])
    assert _buyer_name(rec) == "Heidi Jorgensen"


def test_treats_a_blank_buying_contact_name_as_absent():
    rec = _account(buying="  ", contacts=[_contact("Emily Egan")])
    assert _buyer_name(rec) == "Emily Egan"


def test_strips_surrounding_whitespace():
    assert _buyer_name(_account(buying="  Marilyn Davis ")) == "Marilyn Davis"
