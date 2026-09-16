"""The signature request's CC — the order's rep, from the rep sheet.

Reinstated 2026-09-16 after the 2026-08-06 "never CC" rule: the rep is meant to
be on the thread. The link in the body is a bearer credential, so this is a
deliberate trade, not an oversight — see app/email/signature_template.py.
"""
from app.email import signature_template


def _build(**kwargs):
    return signature_template.build(
        to_email="buyer@store.com", sign_url="https://x/sign/tok", **kwargs
    )


def test_rep_is_ccd():
    assert _build(cc_email="rep@wooden-ships.com")["cc"] == "rep@wooden-ships.com"


def test_no_rep_resolves_to_an_empty_cc():
    # No rep for the writer or the territory — the buyer still gets the email.
    assert _build(cc_email=None)["cc"] == ""
    assert _build()["cc"] == ""


def test_cc_equal_to_the_recipient_is_dropped():
    # A rep ordering for their own account would otherwise be both To and Cc.
    assert _build(cc_email="Buyer@Store.com")["cc"] == ""


def test_addresses_are_trimmed():
    assert _build(cc_email="  rep@wooden-ships.com  ")["cc"] == "rep@wooden-ships.com"


def test_the_body_still_names_nothing_internal():
    body = _build(cc_email="rep@wooden-ships.com")["body"]
    assert "rep@wooden-ships.com" not in body
