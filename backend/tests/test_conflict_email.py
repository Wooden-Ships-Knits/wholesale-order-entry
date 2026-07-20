from app.email import conflict_template


def test_full_draft():
    d = conflict_template.build(
        store_name="Cinnamon Boutique",
        contact_name="Jane Doe",
        to_email="jane@shop.com",
        address="233 S Wacker Dr, Chicago, IL",
        rep_name="Sarah Miller",
        max_minutes=20,
    )
    assert d["to"] == "jane@shop.com"
    assert d["subject"] == "Wooden Ships wholesale — inquiry for Cinnamon Boutique"
    assert d["body"].startswith("Hi Jane,")
    assert "233 S Wacker Dr, Chicago, IL" in d["body"]
    assert "20-minute drive" in d["body"]
    assert d["body"].endswith("Sarah Miller\nWooden Ships")


def test_empty_draft_is_still_sendable():
    d = conflict_template.build()
    assert d["to"] == ""
    assert d["subject"] == "Wooden Ships wholesale — your account inquiry"
    assert d["body"].startswith("Hello,")
    assert "that area" in d["body"]
    assert d["body"].endswith("The Wooden Ships Team\nWooden Ships")


def test_first_name_only():
    assert conflict_template.build(contact_name="  jane  doe ")["body"].startswith("Hi jane,")


def test_never_names_other_stockists():
    """The draft goes to the applicant — neighbor names must not leak into it."""
    d = conflict_template.build(store_name="New Store", address="Chicago, IL")
    assert "A PIED" not in d["body"]
    # the only store named is the recipient's own
    assert d["body"].count("New Store") == 1
