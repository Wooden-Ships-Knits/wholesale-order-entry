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
# One service PER THREAD. google-api-python-client sits on httplib2, which is
# not thread-safe, and FastAPI runs these sync endpoints in a thread pool — the
# order form fires several sheet-backed calls at once on load. Sharing one
# service made concurrent requests corrupt each other's TLS stream
# ("ssl.SSLError: record layer failure"), and because the fetch helpers swallow
# exceptions, the failure was silent: an empty map, and Split quietly optional.
_tls = threading.local()

# Short TTL so a strikethrough edit in the sheet shows up on the form within a
# minute, not five. The sheet is small, so refetching often is cheap.
_CACHE_TTL_SECONDS = 60
_cache: dict[str, tuple[float, Any]] = {}


def _client() -> Any:
    service = getattr(_tls, "service", None)
    if service is None:
        # Building is itself not thread-safe (credential file read + discovery),
        # so serialise construction; the returned object is then this thread's.
        with _lock:
            logger.info("Connecting to Google Sheets (service account)")
            creds = Credentials.from_service_account_file(
                settings.google_credentials_path, scopes=SCOPES
            )
            service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        _tls.service = service
    return service


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
REPS_EMAIL = "Email!A:E"
# The 'Split' tab: Written By | Reps. Every name in the Written_By__c picklist
# belongs to exactly one sales rep; the order-form Split rule compares that rep
# against the rep who owns the sales territory. Lives in the sheet so the sales
# team can add a writer without a deploy.
SPLIT_RANGE = "Split!A:B"
_STATE_CODE_RE = re.compile(r"\b[A-Z]{2}\b")
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


def _territory_map(column: int = 0) -> dict[str, str]:
    """US state code -> REGION column value, read from the region/rep sheet.

    column 0 = the territory label (col A); column 2 = the rep who owns it
    (col C). The rep is what the order form's Split rule compares against —
    parsing the rep out of the label does not work, because labels like
    "Mountain - Taylor & Denise" name a showroom rather than a rep.
    """
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
            value = (row[column] or "").strip() if len(row) > column else ""
            if not value:
                continue
            for code in _STATE_CODE_RE.findall((row[1] or "").upper()):
                if code in US_STATE_CODES:
                    mapping.setdefault(code, value)  # first row wins on overlap
        if not mapping:
            logger.warning(
                "No state->column-%s rows parsed from the territories sheet", column
            )
        return mapping

    if not settings.region_rep_territories_sheet_id:
        return {}

    key = f"territory_map:{column}"
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


def territory_rep_for_state(state_code: str) -> str | None:
    """The rep who owns the territory a state belongs to (REGION column C).

    Drives the order form's Split rule for every account, new or existing —
    an existing account's Salesforce territory label often names a showroom
    ("Mountain - Taylor & Denise") rather than the rep who owns it.
    """
    code = (state_code or "").strip().upper()
    if len(code) != 2:
        return None
    return _territory_map(column=2).get(code)


# The 'Email' tab: # | Sales Territory | Name | Email Address | NOTE (A:E). A
# territory can span several rows (assistants); the FIRST row for a territory is
# the lead rep ("the boss"), whose email we want.
def _normalize_territory(value: str | None) -> str:
    """Match key that ignores spacing/case differences between the REGION tab
    ('CA/ HI - Rande Cohen') and the Email tab ('CA/HI - Rande Cohen')."""
    return re.sub(r"\s+", "", value or "").lower()


def _rep_email_map() -> dict[str, str]:
    """Normalized Sales Territory -> lead rep email (first matching row's Email)."""
    def fetch() -> dict[str, str]:
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
            return {}

        emails: dict[str, str] = {}
        for row in result.get("values", [])[1:]:  # skip the header row
            # A=# B=Sales Territory C=Name D=Email Address E=NOTE
            territory = _normalize_territory(row[1]) if len(row) > 1 else ""
            email = (row[3] or "").strip() if len(row) > 3 else ""
            if territory and email:
                emails.setdefault(territory, email)  # first row = the lead rep
        if not emails:
            logger.warning("No territory->email rows parsed from the reps email sheet")
        return emails

    if not settings.region_rep_territories_sheet_id:
        return {}

    key = "rep_email_map"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value


def split_options() -> list[str]:
    """Selectable values for the order form's "Split with" dropdown.

    The distinct owners in REGION column C — the reps plus "House". Derived
    from the state->rep map rather than the raw column so rows that map to no
    US state (the sheet's 'Test - Sol' row) never reach the form. Sourcing the
    list from the same column the Split rule reads guarantees that whatever the
    rule picks is selectable.
    """
    return sorted(set(_territory_map(column=2).values()))


def writer_rep_map() -> dict[str, str]:
    """"Written By" name -> the sales rep they belong to (the 'Split' tab).

    Returns {} if the sheet is unreadable or unconfigured — the form then treats
    every writer as unmapped, which makes Split optional rather than required.
    Failing open matters here: a sheet outage must not block order entry.
    """
    def fetch() -> dict[str, str]:
        try:
            result = (
                _client()
                .spreadsheets()
                .values()
                .get(
                    spreadsheetId=settings.region_rep_territories_sheet_id,
                    range=SPLIT_RANGE,
                )
                .execute()
            )
        except Exception:
            logger.warning("Could not read the Split tab of the region/rep sheet", exc_info=True)
            return {}

        pairs: dict[str, str] = {}
        for row in result.get("values", [])[1:]:  # skip the header row
            writer = (row[0] or "").strip() if row else ""
            rep = (row[1] or "").strip() if len(row) > 1 else ""
            if writer and rep:
                pairs[writer] = rep
        if not pairs:
            logger.warning("No writer->rep rows parsed from the Split tab")
        return pairs

    if not settings.region_rep_territories_sheet_id:
        return {}

    key = "writer_rep_map"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value


def rep_email_for_territory(territory: str | None) -> str | None:
    """Lead rep email for a Sales Territory value, or None if not found."""
    key = _normalize_territory(territory)
    if not key:
        return None
    return _rep_email_map().get(key)


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
