"""Order email content builders and background scheduling."""
from unittest.mock import MagicMock

from app.email import order_email

CTX = {
    "short_id": "abc12345",
    "season_code": "F26",
    "season_label": "Fall 2026",
    "buyer_name": "A Pied",
    "total_qty": 24,
    "total_amount": 1234.5,
}


def test_admin_email_has_key_facts_and_no_card():
    subject, body = order_email.admin_email(CTX)
    assert "F26" in subject and "A Pied" in subject and "24" in subject
    assert "Fall 2026" in body and "1,234.50" in body and "abc12345" in body
    assert "card" not in body.lower()


def test_buyer_email_is_friendly_and_no_card():
    subject, body = order_email.buyer_email(CTX)
    assert "Fall 2026" in subject
    assert "Thank you" in body and "A Pied" in body
    assert "card" not in body.lower()


def test_schedule_adds_only_admin_when_not_opted_in():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=False, order_copy_email=None,
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 1
    assert bg.add_task.call_args_list[0][0][0] is order_email.send_admin_copy


def test_schedule_adds_buyer_copy_when_opted_in():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=True, order_copy_email="cust@store.com",
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 2
    funcs = [c[0][0] for c in bg.add_task.call_args_list]
    assert order_email.send_admin_copy in funcs
    assert order_email.send_buyer_copy in funcs
    buyer_call = next(
        c for c in bg.add_task.call_args_list if c[0][0] is order_email.send_buyer_copy
    )
    assert buyer_call[0][1] == "cust@store.com"


def test_schedule_skips_buyer_when_opted_in_but_email_missing():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=True, order_copy_email=None,
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 1
