"""Admin order-row serialization — order-copy email passthrough."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.admin import _row


def _order(**over):
    base = dict(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        season_code="F26",
        buyer_name="A Pied",
        account_name="A Pied Boutique",
        order_copy_email="cust@store.com",
        sales_territory=None,
        special_instructions=None,
        ship_email="ship@store.com",
        total_qty=18,
        total_amount=100,
        is_new_account=None,
        has_conflict=None,
        cert_filename=None,
        notes=None,
        status="submitted",
        status_reason=None,
        status_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_row_includes_order_copy_email():
    assert _row(_order())["orderCopyEmail"] == "cust@store.com"


def test_row_order_copy_email_null_when_absent():
    assert _row(_order(order_copy_email=None))["orderCopyEmail"] is None
