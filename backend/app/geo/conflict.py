"""Nearby-stockist conflict check orchestration.

Salesforce candidates (cached) -> haversine pre-filter -> Google drive times
-> verdict. Falls back to straight-line distance when Google is unavailable
so the endpoint never fails because of a third-party hiccup.
"""
import logging

from app.config import settings
from app.geo import distance, drive_time
from app.salesforce import client, mapping

logger = logging.getLogger(__name__)

# Straight-line fallback only: 20 min ≈ 10 mi (30 mph). Documented in the spec.
APPROX_MILES_PER_MINUTE = 0.5

# Distance Matrix allows 25 destinations per request; always ask about at
# least 10 so the drive-time ordering can differ from the straight-line one.
MIN_POOL = 10
MAX_POOL = 25


def find_nearby(lat: float, lng: float, k: int, max_minutes: int) -> dict:
    accounts = [
        mapping.map_nearby_account(r)
        for r in client.list_geocoded_wholesale_accounts()
    ]
    pool = distance.nearest_candidates(lat, lng, accounts, min(max(k, MIN_POOL), MAX_POOL))

    mode = "straight-line"
    if pool and settings.google_maps_server_api_key:
        try:
            minutes = drive_time.drive_minutes(
                (lat, lng),
                [(a["lat"], a["lng"]) for a in pool],
                settings.google_maps_server_api_key,
            )
            for a, m in zip(pool, minutes):
                a["driveMinutes"] = m
            pool.sort(key=lambda a: (a["driveMinutes"] is None, a["driveMinutes"]))
            mode = "drive-time"
        except drive_time.DriveTimeError:
            logger.warning("Drive-time lookup failed — falling back to straight-line", exc_info=True)

    if mode == "straight-line":
        for a in pool:
            a["driveMinutes"] = None  # already sorted by distanceMiles

    neighbors = [
        {key: a[key] for key in ("accountId", "name", "cityState", "distanceMiles", "driveMinutes")}
        for a in pool[:k]
    ]
    if mode == "drive-time":
        conflict = any(
            n["driveMinutes"] is not None and n["driveMinutes"] < max_minutes for n in neighbors
        )
    else:
        conflict = any(n["distanceMiles"] < max_minutes * APPROX_MILES_PER_MINUTE for n in neighbors)

    return {
        "conflict": conflict,
        "mode": mode,
        "maxMinutes": max_minutes,
        "neighbors": neighbors,
    }
