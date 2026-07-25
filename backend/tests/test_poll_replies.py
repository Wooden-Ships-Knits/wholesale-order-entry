"""POST /api/admin/poll-replies — admin/cron trigger that captures inbound
conflict replies then runs the classifier, returning how many of each."""
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.admin.security import require_admin
from app.db.session import get_db
from app.main import app

app.dependency_overrides[require_admin] = lambda: None
client = TestClient(app)


@contextmanager
def _fake_db():
    app.dependency_overrides[get_db] = lambda: object()
    try:
        yield
    finally:
        del app.dependency_overrides[get_db]


def test_poll_replies_returns_capture_and_suggest_counts():
    with _fake_db(), patch(
        "app.routers.admin.inbound.run_poll", return_value=2
    ) as poll, patch(
        "app.routers.admin.conflict_reply.run_classify", return_value=1
    ) as classify:
        resp = client.post("/api/admin/poll-replies")
    assert resp.status_code == 200
    assert resp.json() == {"captured": 2, "suggested": 1}
    poll.assert_called_once()
    classify.assert_called_once()
