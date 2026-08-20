"""Buyer-name resolution from the Salesforce buying contact.

Coverage is on the rule itself: which contact becomes Bill To "Buyer name",
and — just as important — when we refuse to guess and leave it blank.
"""
from app.salesforce.mapping import (
    _account_contacts,
    _buyer_name,
    _is_former,
    map_account,
)


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


def _sf_account(**over):
    """A full Account record, shaped as find_accounts() returns it once the
    Contacts subquery is wired in (Task 4)."""
    base = {
        "Id": "0012v00000AbCdEAAV",
        "Name": "A PIED",
        "BillingStreet": "1 Main St",
        "BillingCity": "Nashville",
        "BillingState": "TN",
        "BillingPostalCode": "37201",
        "ShippingStreet": "1 Main St",
        "ShippingCity": "Nashville",
        "ShippingState": "TN",
        "ShippingPostalCode": "37201",
        "Phone": "(615) 555-0100",
        "Fax": None,
        "ContactBuyingEmail__c": "buyer@apied.com",
        "ContactBuying__r": {"Name": "Kathleen Belavitch", "Title": "Owner"},
        "Contacts": None,
        "Tax_ID_Number__c": None,
        "Tax_ID_Verified__c": False,
        "Tax_ID_Expires__c": None,
        "Salesperson__c": None,
        "SalesTerritory__c": None,
        "Special_Instructions__c": None,
        "Rank__c": None,
    }
    base.update(over)
    return base


def test_map_account_exposes_the_buyer_name():
    assert map_account(_sf_account())["buyerName"] == "Kathleen Belavitch"


def test_map_account_buyer_name_is_none_when_unresolvable():
    rec = _sf_account(ContactBuying__r=None, Contacts=None)
    assert map_account(rec)["buyerName"] is None


def test_map_account_still_reports_the_store_name_separately():
    """Buyer name is a person; name is the store. Conflating them was the bug
    that commit ef1c8e2 fixed — this pins them apart."""
    mapped = map_account(_sf_account())
    assert mapped["name"] == "A PIED"
    assert mapped["buyerName"] == "Kathleen Belavitch"


def test_contacts_lead_with_the_buying_contact():
    rec = _account(
        buying="Kathleen Belavitch",
        buying_title="Owner",
        contacts=[_contact("Someone Else"), _contact("Kathleen Belavitch", "Owner")],
    )
    picked = _account_contacts(rec)
    assert picked[0] == {"name": "Kathleen Belavitch", "title": "Owner", "former": False}


def test_contacts_include_a_buying_contact_filed_under_another_account():
    """25 accounts point ContactBuying__c at a contact that is not their own
    child (SAND PEOPLE - LAHAINA -> Laura Phillipson). The prefilled name must
    still appear in the list, or the field names someone the picker doesn't."""
    rec = _account(buying="Laura Phillipson", contacts=[_contact("Front Desk")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Laura Phillipson", "Front Desk"]


def test_contacts_do_not_repeat_the_buying_contact():
    rec = _account(buying="Emily Egan", contacts=[_contact("Emily Egan")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Emily Egan"]


def test_contact_dedupe_ignores_case():
    rec = _account(buying="Emily Egan", contacts=[_contact("EMILY EGAN")])
    assert len(_account_contacts(rec)) == 1


def test_contacts_flag_former_staff():
    rec = _account(contacts=[_contact("Emma Hopkin", "no longer")])
    assert _account_contacts(rec) == [
        {"name": "Emma Hopkin", "title": "no longer", "former": True}
    ]


def test_contacts_sort_former_staff_last():
    rec = _account(contacts=[
        _contact("Emma Hopkin", "no longer"),
        _contact("Charlotte Glover"),
        _contact("Helen Webster", "no longer"),
        _contact("Sophie Jewell"),
    ])
    assert [c["name"] for c in _account_contacts(rec)] == [
        "Charlotte Glover", "Sophie Jewell", "Emma Hopkin", "Helen Webster",
    ]


def test_a_former_buying_contact_still_leads():
    """Ordering must agree with the prefilled value: _buyer_name() returns the
    buying contact regardless of title, so it cannot sort to the bottom."""
    rec = _account(
        buying="Yolanda", buying_title="no longer", contacts=[_contact("Ann")]
    )
    picked = _account_contacts(rec)
    assert picked[0]["name"] == "Yolanda"
    assert picked[0]["former"] is True


def test_contacts_have_no_title_key_value_when_untitled():
    rec = _account(contacts=[_contact("Katie")])
    assert _account_contacts(rec) == [{"name": "Katie", "title": None, "former": False}]


def test_contacts_skip_blank_names():
    rec = _account(contacts=[_contact("   "), _contact("Heidi Jorgensen")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Heidi Jorgensen"]


def test_contacts_are_empty_when_the_account_has_none():
    assert _account_contacts(_account()) == []


def test_map_account_exposes_the_contact_list():
    rec = _sf_account(Contacts={"records": [{"Name": "Ann", "Title": None}]})
    assert map_account(rec)["contacts"] == [
        {"name": "Kathleen Belavitch", "title": "Owner", "former": False},
        {"name": "Ann", "title": None, "former": False},
    ]


def test_contacts_tolerate_a_bare_contacts_dict():
    """SOQL omits the subquery key shape when an account has no contacts at
    all; a missing "records" must degrade to empty, not raise."""
    rec = _account()
    rec["Contacts"] = {}
    assert _account_contacts(rec) == []


def test_dedupe_ignores_whitespace_against_the_buying_contact():
    rec = _account(buying="Ann ", contacts=[_contact(" Ann"), _contact("Bob")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Ann", "Bob"]


def test_is_former_reads_the_title_the_org_actually_types():
    # Real titles from the org, plus the ones that must NOT match.
    assert _is_former("no longer") is True
    assert _is_former("buyer - no longer there") is True
    assert _is_former("No Longer In Acc (prev asst)") is True
    assert _is_former("Buyer") is False
    assert _is_former(None) is False


def test_a_mailbox_is_not_offered_as_a_buyer():
    """Eight contacts are named things like "Postmaster@coat.com". Offering one
    as a chip would put a real address on a public endpoint and one click from
    a signed order."""
    rec = _account(contacts=[_contact("Kara Shute"), _contact("Postmaster@coat.com")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Kara Shute"]


def test_a_mailbox_does_not_make_a_sole_contact_ambiguous():
    # JOAN SHEPP: one real person plus a receiving mailbox. She is the answer.
    rec = _account(contacts=[_contact("Joan Shepp"), _contact("Receiving@joanshepp.com")])
    assert _buyer_name(rec) == "Joan Shepp"


def test_a_mailbox_is_never_the_buyer_name_even_when_alone():
    rec = _account(contacts=[_contact("Noreply@me.com")])
    assert _buyer_name(rec) is None
    assert _account_contacts(rec) == []
