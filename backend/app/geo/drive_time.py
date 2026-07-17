"""Google Distance Matrix client for the conflict check.

Isolated so a future switch to the newer Routes API is a one-file change.
Only raw coordinates are sent to Google — never account names or ids.
"""
import logging

import requests

logger = logging.getLogger(__name__)

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


class DriveTimeError(Exception):
    """Distance Matrix request failed as a whole (network / auth / quota)."""


def _fmt(point: tuple[float, float]) -> str:
    return f"{point[0]},{point[1]}"


def drive_minutes(
    origin: tuple[float, float],
    destinations: list[tuple[float, float]],
    api_key: str,
    timeout: float = 5.0,
) -> list[int | None]:
    """Driving minutes from origin to each destination (None if unreachable)."""
    try:
        resp = requests.get(
            DISTANCE_MATRIX_URL,
            params={
                "origins": _fmt(origin),
                "destinations": "|".join(_fmt(d) for d in destinations),
                "mode": "driving",
                "key": api_key,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException as exc:
        raise DriveTimeError(f"Distance Matrix request failed: {exc}") from exc

    if payload.get("status") != "OK":
        raise DriveTimeError(f"Distance Matrix status {payload.get('status')}")

    elements = payload["rows"][0]["elements"]
    return [
        round(e["duration"]["value"] / 60) if e.get("status") == "OK" else None
        for e in elements
    ]
