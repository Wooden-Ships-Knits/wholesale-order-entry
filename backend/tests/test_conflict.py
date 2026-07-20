"""find_nearby orchestration: verdicts, sorting, fallback modes."""
from unittest.mock import patch

import pytest

from app.geo import conflict
from app.geo.drive_time import DriveTimeError

CHICAGO = (41.8781, -87.6298)

SF_RECORDS = [
    {"Id": "001A", "Name": "Evanston Wool", "ShippingCity": "Evanston", "ShippingState": "IL",
     "ShippingLatitude": 42.0451, "ShippingLongitude": -87.6877, "lastOrderDate": "2026-05-01"},
    {"Id": "001B", "Name": "Oak Park Knits", "ShippingCity": "Oak Park", "ShippingState": "IL",
     "ShippingLatitude": 41.8850, "ShippingLongitude": -87.7845, "lastOrderDate": "2025-11-20",
     "lastOrderNumber": "SO-0003977", "lastOrderName": "F26 SWEATERS 11/01 - 11/20"},
    {"Id": "001C", "Name": "NYC Flagship", "ShippingCity": "New York", "ShippingState": "NY",
     "ShippingLatitude": 40.7128, "ShippingLongitude": -74.0060, "lastOrderDate": "2024-08-09"},
]


def _patched(minutes=None, key="server-key", side_effect=None):
    return (
        patch("app.geo.conflict.client.list_geocoded_wholesale_accounts", return_value=SF_RECORDS),
        patch("app.geo.conflict.drive_time.drive_minutes",
              return_value=minutes, side_effect=side_effect),
        patch("app.geo.conflict.settings.google_maps_server_api_key", key),
    )


def test_drive_time_mode_conflict_true():
    # Mocked minutes attach in pool order (sorted by straight-line distance
    # from Chicago): 001B Oak Park ~8 mi, 001A Evanston ~12 mi, 001C NYC.
    p1, p2, p3 = _patched(minutes=[9, 25, 700])
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=20)
    assert got["mode"] == "drive-time"
    assert got["conflict"] is True
    assert [n["accountId"] for n in got["neighbors"]] == ["001B", "001A", "001C"]
    assert got["neighbors"][0]["driveMinutes"] == 9
    assert got["neighbors"][0]["distanceMiles"] > 0
    assert got["neighbors"][0]["lastOrder"] == "2025-11-20"  # 001B Oak Park
    assert got["neighbors"][0]["lastOrderNumber"] == "SO-0003977"
    assert got["neighbors"][0]["lastOrderName"] == "F26 SWEATERS 11/01 - 11/20"


def test_drive_time_mode_conflict_false_at_threshold():
    # exactly the threshold is NOT a conflict (strictly less than)
    p1, p2, p3 = _patched(minutes=[20, 45, 700])
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=20)
    assert got["conflict"] is False


def test_unreachable_neighbors_sort_last():
    p1, p2, p3 = _patched(minutes=[None, 15, 700])
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=20)
    assert got["neighbors"][-1]["driveMinutes"] is None
    assert got["conflict"] is True


def test_truncates_to_k():
    p1, p2, p3 = _patched(minutes=[9, 25, 700])
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=1, max_minutes=20)
    assert len(got["neighbors"]) == 1
    assert got["neighbors"][0]["accountId"] == "001B"


def test_no_key_falls_back_to_straight_line():
    p1, p2, p3 = _patched(key="")
    with p1, p2 as dm, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=20)
    dm.assert_not_called()
    assert got["mode"] == "straight-line"
    assert all(n["driveMinutes"] is None for n in got["neighbors"])
    # 20 min * 0.5 mi/min = 10 mi: Oak Park (~8 mi) conflicts, Evanston (~12 mi) doesn't
    assert got["conflict"] is True


def test_google_failure_falls_back_to_straight_line():
    p1, p2, p3 = _patched(side_effect=DriveTimeError("denied"))
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=20)
    assert got["mode"] == "straight-line"


def test_straight_line_no_conflict_when_all_far():
    p1, p2, p3 = _patched(key="")
    with p1, p2, p3:
        got = conflict.find_nearby(*CHICAGO, k=3, max_minutes=5)  # 2.5 mi radius
    assert got["conflict"] is False
    assert got["maxMinutes"] == 5
