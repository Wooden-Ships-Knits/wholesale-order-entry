"""GET /api/accounts/nearby endpoint wiring (conflict logic tested in test_conflict)."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

RESULT = {"conflict": False, "mode": "straight-line", "maxMinutes": 20, "neighbors": []}


def test_nearby_happy_path_uses_default_threshold():
    with patch("app.routers.accounts.conflict.find_nearby", return_value=RESULT) as fn:
        resp = client.get("/api/accounts/nearby", params={"lat": 41.88, "lng": -87.63})
    assert resp.status_code == 200
    assert resp.json() == RESULT
    fn.assert_called_once_with(41.88, -87.63, 5, 20)


def test_nearby_passes_overrides():
    with patch("app.routers.accounts.conflict.find_nearby", return_value=RESULT) as fn:
        client.get(
            "/api/accounts/nearby",
            params={"lat": 1, "lng": 2, "k": 10, "maxMinutes": 45},
        )
    fn.assert_called_once_with(1.0, 2.0, 10, 45)


def test_nearby_rejects_bad_latitude():
    resp = client.get("/api/accounts/nearby", params={"lat": 123, "lng": 0})
    assert resp.status_code == 422


def test_nearby_requires_coordinates():
    resp = client.get("/api/accounts/nearby")
    assert resp.status_code == 422
