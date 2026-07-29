"""POST /api/admin/orders/{id}/conflict-resolution — admin records the outcome
of a conflict inquiry (cleared / real conflict) so the row closes."""
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.admin.security import require_admin
from app.db.session import get_db
from app.main import app

app.dependency_overrides[require_admin] = lambda: None
client = TestClient(app)


class _FakeSession:
    """get() returns the preset order (or None → 404); commit() records."""

    def __init__(self, order):
        self.order = order
        self.committed = False

    def get(self, _model, _id):
        return self.order

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


@contextmanager
def _fake_db(order):
    session = _FakeSession(order)
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        del app.dependency_overrides[get_db]


def _order():
    # Only the fields _row() and the endpoint touch — enough to serialize.
    return SimpleNamespace(
        id="abc",
        shortId="abc",
        created_at=None,
        season_code="F26",
        account_name="A Pied Boutique",
        order_copy_email=None,
        sales_territory=None,
        special_instructions=None,
        ship_email="ship@store.com",
        buyer_name="A Pied",
        total_qty=18,
        total_amount=100,
        is_new_account=True,
        has_conflict=True,
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


def test_cleared_stamps_resolution_and_time():
    order = _order()
    with _fake_db(order) as session:
        resp = client.post(
            "/api/admin/orders/abc/conflict-resolution",
            json={"outcome": "cleared", "note": "Different customer base."},
        )
    assert resp.status_code == 200
    assert order.conflict_resolution == "cleared"
    assert order.conflict_resolved_at is not None
    assert order.conflict_resolution_note == "Different customer base."
    assert session.committed
    body = resp.json()
    assert body["conflictResolution"] == "cleared"
    assert body["conflictResolvedAt"] is not None


def test_real_conflict_outcome_accepted():
    order = _order()
    with _fake_db(order):
        resp = client.post(
            "/api/admin/orders/abc/conflict-resolution",
            json={"outcome": "real_conflict"},
        )
    assert resp.status_code == 200
    assert order.conflict_resolution == "real_conflict"
    # note is optional — absent means null, not empty string
    assert order.conflict_resolution_note is None


def test_unknown_outcome_rejected():
    order = _order()
    with _fake_db(order):
        resp = client.post(
            "/api/admin/orders/abc/conflict-resolution",
            json={"outcome": "maybe"},
        )
    assert resp.status_code == 422


def test_missing_order_returns_404():
    with _fake_db(None):
        resp = client.post(
            "/api/admin/orders/nope/conflict-resolution",
            json={"outcome": "cleared"},
        )
    assert resp.status_code == 404
