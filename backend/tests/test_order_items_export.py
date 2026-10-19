"""Order-line serialization for the Excel export's "Order items" sheet."""
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.routers.admin import OrderItemsRequest, _item_row


def _item(**over):
    base = dict(
        order_id=uuid.uuid4(),
        code="K57-101",
        style_name="Cable Crew",
        color="Navy",
        qty_xs=2,
        qty_sm=3,
        qty_ml=2,
        line_qty=7,
        unit_price=Decimal("68.00"),
        line_total=Decimal("476.00"),
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_item_row_fields():
    item = _item()
    row = _item_row(item)
    assert row == {
        "orderId": str(item.order_id),
        "code": "K57-101",
        "styleName": "Cable Crew",
        "color": "Navy",
        "qtyXs": 2,
        "qtySm": 3,
        "qtyMl": 2,
        "lineQty": 7,
        "unitPrice": 68.0,
        "lineTotal": 476.0,
    }


def test_item_row_money_is_a_number_for_excel():
    row = _item_row(_item())
    assert isinstance(row["unitPrice"], float)
    assert isinstance(row["lineTotal"], float)


def test_request_rejects_non_uuid_ids():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        OrderItemsRequest(ids=["2018f7d0"])
