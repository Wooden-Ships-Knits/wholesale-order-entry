"""Google Distance Matrix client parsing/errors (HTTP mocked)."""
from unittest.mock import Mock, patch

import pytest
import requests

from app.geo.drive_time import DriveTimeError, drive_minutes

ORIGIN = (41.8781, -87.6298)
DESTS = [(42.0451, -87.6877), (40.7128, -74.0060)]


def _response(payload, status=200):
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = Mock()
    return resp


def test_parses_minutes_per_destination():
    payload = {
        "status": "OK",
        "rows": [{"elements": [
            {"status": "OK", "duration": {"value": 540}},   # 9 min
            {"status": "OK", "duration": {"value": 45720}}, # 762 min
        ]}],
    }
    with patch("app.geo.drive_time.requests.get", return_value=_response(payload)) as get:
        assert drive_minutes(ORIGIN, DESTS, api_key="k") == [9, 762]
    params = get.call_args.kwargs["params"]
    assert params["origins"] == "41.8781,-87.6298"
    assert params["destinations"] == "42.0451,-87.6877|40.7128,-74.006"
    assert params["mode"] == "driving"


def test_unreachable_element_is_none():
    payload = {
        "status": "OK",
        "rows": [{"elements": [
            {"status": "ZERO_RESULTS"},
            {"status": "OK", "duration": {"value": 120}},
        ]}],
    }
    with patch("app.geo.drive_time.requests.get", return_value=_response(payload)):
        assert drive_minutes(ORIGIN, DESTS, api_key="k") == [None, 2]


def test_top_level_error_raises():
    with patch("app.geo.drive_time.requests.get",
               return_value=_response({"status": "REQUEST_DENIED", "rows": []})):
        with pytest.raises(DriveTimeError):
            drive_minutes(ORIGIN, DESTS, api_key="bad")


def test_network_error_raises():
    with patch("app.geo.drive_time.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(DriveTimeError):
            drive_minutes(ORIGIN, DESTS, api_key="k")
