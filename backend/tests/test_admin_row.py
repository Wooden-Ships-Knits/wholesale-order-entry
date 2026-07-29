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
        sf_account_id=None,
        sf_account_created_at=None,
        sf_order_id=None,
        sf_order_number=None,
        conflict_email_sent_at=None,
        tax_cert_email_sent_at=None,
        conflict_resolution=None,
        conflict_resolved_at=None,
        conflict_resolution_note=None,
        conflict_ai_outcome=None,
        conflict_ai_confidence=None,
        conflict_ai_reason=None,
        conflict_ai_at=None,
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


def test_row_conflict_resolution_null_when_unresolved():
    row = _row(_order())
    assert row["conflictResolution"] is None
    assert row["conflictResolvedAt"] is None
    assert row["conflictResolutionNote"] is None


def test_row_exposes_conflict_resolution_when_set():
    resolved = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    row = _row(
        _order(
            conflict_resolution="cleared",
            conflict_resolved_at=resolved,
            conflict_resolution_note="Rep says different segment.",
        )
    )
    assert row["conflictResolution"] == "cleared"
    assert row["conflictResolvedAt"] == resolved.isoformat()
    assert row["conflictResolutionNote"] == "Rep says different segment."


def test_row_ai_suggestion_null_when_absent():
    row = _row(_order())
    assert row["conflictAiOutcome"] is None
    assert row["conflictAiConfidence"] is None
    assert row["conflictAiReason"] is None


def test_row_exposes_ai_suggestion_when_set():
    from decimal import Decimal

    row = _row(
        _order(
            conflict_ai_outcome="cleared",
            conflict_ai_confidence=Decimal("0.90"),
            conflict_ai_reason="Rep said proceed.",
            conflict_ai_at=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
        )
    )
    assert row["conflictAiOutcome"] == "cleared"
    assert row["conflictAiConfidence"] == 0.9  # serialized as float
    assert row["conflictAiReason"] == "Rep said proceed."
