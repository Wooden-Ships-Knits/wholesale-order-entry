"""Great-circle distance + nearest-candidate selection (pure Python).

The candidate pool is small (~4.4k geocoded wholesale accounts), so exact
KNN by sorting is faster and simpler than any spatial index.
"""
from math import asin, cos, radians, sin, sqrt
from typing import Any

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlng1, rlat2, rlng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(a))


def nearest_candidates(
    lat: float, lng: float, accounts: list[dict[str, Any]], pool_size: int
) -> list[dict[str, Any]]:
    """The pool_size accounts nearest to (lat, lng), each with distanceMiles set."""
    with_distance = [
        {**a, "distanceMiles": round(haversine_miles(lat, lng, a["lat"], a["lng"]), 1)}
        for a in accounts
    ]
    with_distance.sort(key=lambda a: a["distanceMiles"])
    return with_distance[:pool_size]
