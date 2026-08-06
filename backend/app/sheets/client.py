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

# Short TTL so a strikethrough edit in the sheet shows up on the form within a
# minute, not five. The sheet is small, so refetching often is cheap.
_CACHE_TTL_SECONDS = 60
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


def get_values(
    spreadsheet_id: str,
    worksheet_name: str,
    value_render_option: str = "FORMATTED_VALUE",
) -> list[list[str]]:
    """Every populated row of one worksheet, as a rectangular list of strings.

    The generic reader the DMM report needs — the ship-window `_read` above is
    tied to one spreadsheet and reads cell formatting, which this doesn't.

    Rows are padded to the widest row: the Sheets API drops trailing empty
    cells, so rows come back ragged and `DataFrame(rows[1:], columns=rows[0])`
    would raise on any row shorter than its header.

    value_render_option="UNFORMATTED_VALUE" yields raw values — dates arrive as
    Google serial numbers, which is what the email-schedule parsing expects.
    """
    result = (
        _client()
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"'{worksheet_name}'",
            valueRenderOption=value_render_option,
        )
        .execute()
    )
    rows = result.get("values", [])
    if not rows:
        logger.warning("Worksheet %r in %s is empty", worksheet_name, spreadsheet_id[:8])
        return []
    width = max(len(r) for r in rows)
    return [list(r) + [""] * (width - len(r)) for r in rows]


def _read(season_code: str) -> list[list[tuple[str, bool]]]:
    """Rows for one season's worksheet as (value, struck) cells.

    Uses spreadsheets.get with grid data so cell formatting (strikethrough)
    is visible — values().get() does not return formatting. Empty list if
    the tab is missing.
    """
    try:
        result = (
            _client()
            .spreadsheets()
            .get(
                spreadsheetId=settings.shipping_window_sheet_id,
                ranges=[f"'{season_code}'!{RANGE_COLUMNS}"],
                includeGridData=True,
                fields=(
                    "sheets.data.rowData.values("
                    "formattedValue,"
                    "effectiveFormat.textFormat.strikethrough)"
                ),
            )
            .execute()
        )
    except Exception:
        logger.warning("No ship-window sheet for season %s", season_code, exc_info=True)
        return []

    sheets = result.get("sheets", [])
    data = sheets[0].get("data", []) if sheets else []
    row_data = data[0].get("rowData", []) if data else []

    rows: list[list[tuple[str, bool]]] = []
    for row in row_data:
        cells: list[tuple[str, bool]] = []
        for cell in row.get("values", []):
            value = (cell.get("formattedValue") or "").strip()
            struck = (
                cell.get("effectiveFormat", {})
                .get("textFormat", {})
                .get("strikethrough", False)
            )
            cells.append((value, struck))
        rows.append(cells)
    return rows


# A ship window looks like "7/1-30" or "12/1-10". Matching the value shape
# rather than a row offset keeps this working across tabs that differ in
# leading blank rows, titles, and even stacked tables (S26 has two).
_WINDOW_RE = re.compile(r"^\d{1,2}/\d{1,2}-\d{1,2}$")


# --------------------------------------------------------- region/rep territory
# The territories sheet's first tab: Territory | States | Rep. The States cell
# is a comma-separated list of 2-letter US state codes (e.g. "AK,AZ,NE,NV"),
# sometimes mixed with descriptive text ("DC Metro/Suburb, DE, MD, NJ, PA") —
# so we pull out standalone 2-letter codes and keep only real US states.
TERRITORY_RANGE = "REGION!A:C"
# Email tab: A=# B=Sales Territory C=Name D=Email Address E=NOTE F=Email Address real
#
# Column D is the address orders are sent to, and it is NOT always the person's
# own: an assistant's row carries their principal's address on purpose (Julie
# Zipperer -> rande@randecohen.com), so the order lands with whoever handles it.
# Column F holds their real, personal address — reference only, never sent to.
REPS_EMAIL = "Email!A:F"
_STATE_CODE_RE = re.compile(r"\b[A-Z]{2}\b")
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


def _territory_map() -> dict[str, str]:
    """US state code -> territory label, read from the region/rep sheet."""
    def fetch() -> dict[str, str]:
        try:
            result = (
                _client()
                .spreadsheets()
                .values()
                .get(
                    spreadsheetId=settings.region_rep_territories_sheet_id,
                    range=TERRITORY_RANGE,
                )
                .execute()
            )
        except Exception:
            logger.warning("Could not read the region/rep territories sheet", exc_info=True)
            return {}

        mapping: dict[str, str] = {}
        for row in result.get("values", [])[1:]:  # skip the header row
            if len(row) < 2:
                continue
            territory = (row[0] or "").strip()
            if not territory:
                continue
            for code in _STATE_CODE_RE.findall((row[1] or "").upper()):
                if code in US_STATE_CODES:
                    mapping.setdefault(code, territory)  # first row wins on overlap
        if not mapping:
            logger.warning("No state->territory rows parsed from the territories sheet")
        return mapping

    if not settings.region_rep_territories_sheet_id:
        return {}

    key = "territory_map"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value


def territory_for_state(state_code: str) -> str | None:
    """Territory label for a 2-letter US state code, or None if unmapped."""
    code = (state_code or "").strip().upper()
    if len(code) != 2:
        return None
    return _territory_map().get(code)


# The 'Email' tab is read into two indexes off one fetch:
#
#   by NAME (column C)      — who wrote the order. The primary lookup, because
#                             the person who wrote it is the person who should
#                             get it back, wherever the store happens to sit.
#   by TERRITORY (column B) — the fallback, for a customer-filled order, which
#                             has no writer. A territory can span several rows
#                             (assistants); the FIRST is the lead rep.
#
# Both resolve to column D, which is the address to send to and is deliberately
# not always the row's own person — see the REPS_EMAIL note above.
def _normalize_territory(value: str | None) -> str:
    """Match key that ignores spacing/case differences between the REGION tab
    ('CA/ HI - Rande Cohen') and the Email tab ('CA/HI - Rande Cohen')."""
    return re.sub(r"\s+", "", value or "").lower()


def _normalize_name(value: str | None) -> str:
    """Match key for a person's name: spacing and case don't have to agree
    between the Salesforce 'Written By' picklist and column C of the sheet."""
    return re.sub(r"\s+", "", value or "").lower()


def _rep_email_maps() -> tuple[dict[str, str], dict[str, str]]:
    """(by normalized name, by normalized territory) -> email address."""
    def fetch() -> tuple[dict[str, str], dict[str, str]]:
        try:
            result = (
                _client()
                .spreadsheets()
                .values()
                .get(
                    spreadsheetId=settings.region_rep_territories_sheet_id,
                    range=REPS_EMAIL,
                )
                .execute()
            )
        except Exception:
            logger.warning("Could not read the reps email sheet", exc_info=True)
            return {}, {}

        by_name: dict[str, str] = {}
        by_territory: dict[str, str] = {}
        for row in result.get("values", [])[1:]:  # skip the header row
            # A=# B=Sales Territory C=Name D=Email Address E=NOTE F=real address
            territory = _normalize_territory(row[1]) if len(row) > 1 else ""
            name = _normalize_name(row[2]) if len(row) > 2 else ""
            email = (row[3] or "").strip() if len(row) > 3 else ""
            if not email:
                continue
            # setdefault both: one name can appear on several territory rows
            # (Kitty Tally covers three), and one territory on several name rows.
            if name:
                by_name.setdefault(name, email)
            if territory:
                by_territory.setdefault(territory, email)  # first row = lead rep
        if not by_name and not by_territory:
            logger.warning("No usable rows parsed from the reps email sheet")
        return by_name, by_territory

    if not settings.region_rep_territories_sheet_id:
        return {}, {}

    key = "rep_email_maps"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value


def rep_email_for_writer(name: str | None) -> str | None:
    """Email for an 'Order written by' name (column C -> column D), or None."""
    key = _normalize_name(name)
    if not key:
        return None
    return _rep_email_maps()[0].get(key)


def rep_email_for_territory(territory: str | None) -> str | None:
    """Lead rep email for a Sales Territory value, or None if not found."""
    key = _normalize_territory(territory)
    if not key:
        return None
    return _rep_email_maps()[1].get(key)


def all_rep_emails() -> set[str]:
    """Every address the Email tab can route an order to, lowercased.

    Used only by the dev mail rewriter, to tell a rep recipient from a buyer so
    each goes to its own test inbox. Off the same cached fetch as the lookups,
    so it costs nothing extra; an unreadable sheet yields an empty set and the
    rewriter simply treats everyone as a buyer — still nobody real.
    """
    by_name, by_territory = _rep_email_maps()
    return {e.lower() for e in (*by_name.values(), *by_territory.values()) if e}


def rep_email_for_order(written_by: str | None, territory: str | None) -> str | None:
    """The rep address for one order: whoever wrote it, else whoever owns the
    territory.

    Written By is the authority (2026-08-06): a rep who writes an order for a
    store outside their own patch still wants it back, and the territory owner
    getting it instead was the wrong person twice over. Customer-filled orders
    carry no writer, so those fall back to the territory — which is what the
    whole system did before.
    """
    return rep_email_for_writer(written_by) or rep_email_for_territory(territory)


def list_ship_windows(season_code: str) -> list[str]:
    """Distinct ship windows offered for a season, in sheet order."""
    def fetch() -> list[str]:
        windows: list[str] = []
        for row in _read(season_code):
            # Column 0 is the collection name; ship windows follow.
            for value, struck in row[1:]:
                if struck:
                    continue  # window closed — don't offer it
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
