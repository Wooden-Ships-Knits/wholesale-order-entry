"""Haversine + candidate selection for the nearby-stockist conflict check."""
import pytest

from app.geo.distance import haversine_miles, nearest_candidates
from app.salesforce.mapping import map_nearby_account

NYC = (40.7128, -74.0060)
LA = (34.0522, -118.2437)
CHICAGO = (41.8781, -87.6298)
EVANSTON = (42.0451, -87.6877)


def test_haversine_known_city_pair():
    # Great-circle NYC <-> LA is ~2446 miles
    assert haversine_miles(*NYC, *LA) == pytest.approx(2446, rel=0.01)


def test_haversine_zero_distance():
    assert haversine_miles(*CHICAGO, *CHICAGO) == 0


def test_haversine_short_hop():
    # Chicago Loop <-> Evanston is ~12 miles great-circle
    assert haversine_miles(*CHICAGO, *EVANSTON) == pytest.approx(12, rel=0.15)


def _acct(name, lat, lng):
    return {
        "accountId": name, "name": name, "cityState": "",
        "lastOrder": "2026-01-15", "lat": lat, "lng": lng,
    }


def test_nearest_candidates_sorted_and_limited():
    accounts = [_acct("la", *LA), _acct("evanston", *EVANSTON), _acct("nyc", *NYC)]
    got = nearest_candidates(*CHICAGO, accounts, pool_size=2)
    assert [a["accountId"] for a in got] == ["evanston", "nyc"]
    assert got[0]["distanceMiles"] < got[1]["distanceMiles"]
    assert got[0]["distanceMiles"] == round(got[0]["distanceMiles"], 1)


def test_map_nearby_account():
    rec = {
        "Id": "001x",
        "Name": "Lakeview Knits",
        "ShippingCity": "Chicago",
        "ShippingState": "IL",
        "ShippingLatitude": 41.9,
        "ShippingLongitude": -87.6,
        "lastOrderDate": "2026-03-02",
    }
    assert map_nearby_account(rec) == {
        "accountId": "001x",
        "name": "Lakeview Knits",
        "cityState": "Chicago, IL",
        "lastOrder": "2026-03-02",
        "lat": 41.9,
        "lng": -87.6,
    }
