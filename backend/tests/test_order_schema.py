"""Schema tests for POST /api/orders payload — new 2026-07-16 form fields."""
import base64

import pytest
from pydantic import ValidationError

from app.schemas.order import OrderSubmission

BASE = {
    "season": "F26",
    "shipTo": {"email": "buyer@store.com"},
}


def _sub(**extra) -> OrderSubmission:
    return OrderSubmission.model_validate({**BASE, **extra})


def test_new_top_level_fields_parse_from_camel_case():
    sub = _sub(shipWindow="08/01 - 08/31  2026", filledBy="rep", notes="Call before shipping")
    assert sub.ship_window == "08/01 - 08/31  2026"
    assert sub.filled_by == "rep"
    assert sub.notes == "Call before shipping"


def test_new_fields_default_empty_for_old_payloads():
    sub = _sub()
    assert sub.ship_window == ""
    assert sub.filled_by == ""
    assert sub.notes == ""
    assert sub.payment.method == ""
    assert sub.payment.approval_before_charge is None
    assert sub.tax_exemption.cert_file is None
    assert sub.bill_to.lat is None and sub.bill_to.lng is None


def test_address_coordinates_parse():
    sub = _sub(
        billTo={"buyerName": "A", "lat": 41.878113, "lng": -87.629799},
        shipTo={"email": "buyer@store.com", "lat": 34.052235, "lng": -118.243683},
    )
    assert sub.bill_to.lat == pytest.approx(41.878113)
    assert sub.ship_to.lng == pytest.approx(-118.243683)


def test_payment_method_parses():
    sub = _sub(payment={"method": "link"})
    assert sub.payment.method == "link"


def test_cert_file_parses_and_decodes():
    content = base64.b64encode(b"%PDF-1.4 fake").decode()
    sub = _sub(taxExemption={"certFile": {"name": "resale-cert.pdf", "contentBase64": content}})
    assert sub.tax_exemption.cert_file.decoded() == b"%PDF-1.4 fake"


def test_cert_file_rejects_disallowed_extension():
    content = base64.b64encode(b"MZ fake exe").decode()
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "evil.exe", "contentBase64": content}})


def test_cert_file_rejects_oversize():
    # > 10 MB decoded
    content = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "big.pdf", "contentBase64": content}})


def test_cert_file_rejects_invalid_base64():
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "cert.pdf", "contentBase64": "not@base64!!"}})


def test_order_copy_defaults_off_for_old_payloads():
    sub = _sub()
    assert sub.terms.order_copy is False
    assert sub.terms.order_copy_email is None


def test_order_copy_with_email_parses_from_camel_case():
    sub = _sub(terms={"orderCopy": True, "orderCopyEmail": "cust@store.com"})
    assert sub.terms.order_copy is True
    assert sub.terms.order_copy_email == "cust@store.com"


def test_order_copy_true_requires_an_email():
    with pytest.raises(ValidationError):
        _sub(terms={"orderCopy": True})


def test_order_copy_true_rejects_invalid_email():
    with pytest.raises(ValidationError):
        _sub(terms={"orderCopy": True, "orderCopyEmail": "not-an-email"})
