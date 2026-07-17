"""Ship windows from the planning Google Sheet.

One worksheet per season code ("F26", "S27"). Layout (columns B:Q):

    B                  C        D        E     ...
    ------------------------------------------------
    FALL 2026                                        <- title row
    COLLECTION         SHIP WINDOWS                  <- header row (merged)
    ESSENTIALS COTTON  7/1-30   8/1-30   9/1-20 ...  <- one row per collection
    GAME DAY           7/1-30   8/1-30   9/1-20 ...

Collections do not all offer the same windows (a row may start with blanks),
and the number of rows/columns differs per season — so the option list is the
distinct non-empty values across every collection row, kept in column order.

Read-only, service-account auth, cached like the Salesforce calls.
"""
import logging
import re
import threading
import time
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
RANGE_COLUMNS = "B:Q"

_lock = threading.Lock()
_service: Any = None

_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}


def _client() -> Any:
    global _service
    with _lock:
        if _service is None:
            logger.info("Connecting to Google Sheets (service account)")
            creds = Credentials.from_service_account_file(
                settings.google_credentials_path, scopes=SCOPES
            )
            _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return _service


def _read(season_code: str) -> list[list[str]]:
    """Raw rows for one season's worksheet. Empty list if the tab is missing."""
    try:
        result = (
            _client()
            .spreadsheets()
            .values()
            .get(
                spreadsheetId=settings.shipping_window_sheet_id,
                range=f"'{season_code}'!{RANGE_COLUMNS}",
            )
            .execute()
        )
        return result.get("values", [])
    except Exception:
        # A season with no tab yet is normal — don't blow up the form.
        logger.warning("No ship-window sheet for season %s", season_code, exc_info=True)
        return []


# A ship window looks like "7/1-30" or "12/1-10". Matching the value shape
# rather than a row offset keeps this working across tabs that differ in
# leading blank rows, titles, and even stacked tables (S26 has two).
_WINDOW_RE = re.compile(r"^\d{1,2}/\d{1,2}-\d{1,2}$")


def list_ship_windows(season_code: str) -> list[str]:
    """Distinct ship windows offered for a season, in sheet order."""
    def fetch() -> list[str]:
        windows: list[str] = []
        for row in _read(season_code):
            # Column 0 is the collection name; ship windows follow.
            for cell in row[1:]:
                value = (cell or "").strip()
                if _WINDOW_RE.match(value) and value not in windows:
                    windows.append(value)
        if not windows:
            logger.warning("No ship windows parsed for season %s", season_code)
        return windows

    if not settings.shipping_window_sheet_id:
        return []

    key = f"ship_windows:{season_code}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value
