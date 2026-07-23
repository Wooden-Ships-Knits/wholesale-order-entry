"""POST /api/send-email — admin-only send of a drafted email via SMTP."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from fastapi.testclient import TestClient

from app.admin.security import require_admin
from app.config import Settings
from app.db.session import get_db
from app.main import app

app.dependency_overrides[require_admin] = lambda: None
client = TestClient(app)


@contextmanager
def mail_configured(value: bool):
    # mail_configured is a property, so patch it on the class.
    with patch.object(
        Settings, "mail_configured", new_callable=PropertyMock, return_value=value
    ):
        yield

PAYLOAD = {
    "to": "rep@wooden-ships.com",
    "cc": "manager@wooden-ships.com",
    "subject": "Wholesale inquiry",
    "body": "Hi Kitty Tally,\n\nPlease see the inquiry below.",
}


def test_send_email_happy_path_passes_cc_to_mailer():
    with mail_configured(True), patch(
        "app.routers.send_email.mailer.send_email", return_value=True
    ) as send:
        resp = client.post("/api/send-email", json=PAYLOAD)
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    send.assert_called_once_with(
        PAYLOAD["to"], PAYLOAD["subject"], PAYLOAD["body"], cc=PAYLOAD["cc"]
    )


def test_send_email_requires_cc():
    resp = client.post("/api/send-email", json={**PAYLOAD, "cc": ""})
    assert resp.status_code == 422


def test_send_email_requires_to():
    resp = client.post("/api/send-email", json={**PAYLOAD, "to": ""})
    assert resp.status_code == 422


def test_send_email_503_when_mail_unconfigured():
    with mail_configured(False):
        resp = client.post("/api/send-email", json=PAYLOAD)
    assert resp.status_code == 503


def test_send_email_502_when_send_fails():
    with mail_configured(True), patch(
        "app.routers.send_email.mailer.send_email", return_value=False
    ):
        resp = client.post("/api/send-email", json=PAYLOAD)
    assert resp.status_code == 502


class _FakeSession:
    """Minimal Session stand-in: get() returns the order, commit() records it."""

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


def test_send_email_stamps_conflict_order_on_success():
    order = SimpleNamespace(conflict_email_sent_at=None, tax_cert_email_sent_at=None)
    with _fake_db(order) as session, mail_configured(True), patch(
        "app.routers.send_email.mailer.send_email", return_value=True
    ):
        resp = client.post("/api/send-email", json={**PAYLOAD, "orderId": "abc", "kind": "conflict"})
    assert resp.status_code == 200
    assert order.conflict_email_sent_at is not None
    assert order.tax_cert_email_sent_at is None
    assert session.committed


def test_send_email_stamps_tax_cert_order_on_success():
    order = SimpleNamespace(conflict_email_sent_at=None, tax_cert_email_sent_at=None)
    with _fake_db(order) as session, mail_configured(True), patch(
        "app.routers.send_email.mailer.send_email", return_value=True
    ):
        resp = client.post("/api/send-email", json={**PAYLOAD, "orderId": "abc", "kind": "tax_cert"})
    assert resp.status_code == 200
    assert order.tax_cert_email_sent_at is not None
    assert order.conflict_email_sent_at is None
    assert session.committed


def test_send_email_rejects_unknown_kind():
    resp = client.post("/api/send-email", json={**PAYLOAD, "orderId": "abc", "kind": "bogus"})
    assert resp.status_code == 422
