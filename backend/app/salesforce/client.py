"""Salesforce client: session management, SOQL helpers, query services.

All calls happen backend-side only. Credentials come from settings (.env).
The session is created lazily and re-created automatically on expiry.
"""
import logging
import re
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable

from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceExpiredSession

from app.config import settings
from app.salesforce import mapping

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_sf: Salesforce | None = None

# Small in-memory TTL cache: the catalog changes rarely and a season's
# product list is ~2.6k rows from Salesforce.
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, Any]] = {}


def _connect() -> Salesforce:
    logger.info("Connecting to Salesforce (domain=%s)", settings.salesforce_domain)
    return Salesforce(
        username=settings.salesforce_username,
        password=settings.salesforce_password,
        security_token=settings.salesforce_security_token,
        domain=settings.salesforce_domain,
    )


def _client() -> Salesforce:
    global _sf
    with _lock:
        if _sf is None:
            _sf = _connect()
        return _sf


def _reset_client() -> None:
    global _sf
    with _lock:
        _sf = None


def query_all(soql: str) -> list[dict[str, Any]]:
    """Run a SOQL query, re-authenticating once on session expiry."""
    try:
        return _client().query_all(soql)["records"]
    except SalesforceExpiredSession:
        logger.info("Salesforce session expired — re-authenticating")
        _reset_client()
        return _client().query_all(soql)["records"]


def create_account(fields: dict[str, Any]) -> str:
    """Create a Salesforce Account, re-authenticating once on session expiry.

    Returns the new Account Id. Raises on any Salesforce error (duplicate rules,
    validation rules, missing permission) so the caller can surface it — this is
    a write to the live org, never fail silently.
    """
    def do() -> dict[str, Any]:
        return _client().Account.create(fields)

    try:
        result = do()
    except SalesforceExpiredSession:
        logger.info("Salesforce session expired — re-authenticating")
        _reset_client()
        result = do()

    if not result.get("success"):
        raise RuntimeError(f"Salesforce rejected the account create: {result.get('errors')}")
    return result["id"]


def get_wholesale_pricebook_id(season_code: str) -> str | None:
    """Id of the '<season> Wholesale' price book, or None if not found."""
    target = mapping.pricebook_name_for_season(season_code)
    for pb in list_wholesale_pricebooks():
        if pb.get("Name") == target:
            return pb["Id"]
    return None


def kugamon_detail_ids(product2_ids: list[str]) -> dict[str, str]:
    """Product2 id -> kugo2p__AdditionalProductDetail__c id.

    The order line's kugo2p__Product__c references Kugamon's product-detail
    record, not Product2 (we store Product2 ids). One detail per Product2.
    """
    ids = [p for p in dict.fromkeys(product2_ids) if p]
    if not ids:
        return {}
    inlist = "','".join(soql_str(p) for p in ids)
    rows = query_all(
        f"SELECT Id, {mapping.KUGAMON_DETAIL_REFERENCE_PRODUCT} "
        f"FROM {mapping.KUGAMON_PRODUCT_DETAIL} "
        f"WHERE {mapping.KUGAMON_DETAIL_REFERENCE_PRODUCT} IN ('{inlist}')"
    )
    return {r[mapping.KUGAMON_DETAIL_REFERENCE_PRODUCT]: r["Id"] for r in rows}


def _norm_picklist(value: str | None) -> str:
    """Whitespace-insensitive, lowercased key for picklist matching."""
    return re.sub(r"\s+", "", value or "").lower()


def match_order_territory(value: str | None) -> str | None:
    """Match our sales-territory string to the order's SalesTerritory picklist,
    ignoring spacing/case (REGION tab has 'CA/ HI', the picklist 'CA/HI'). Returns
    the exact picklist value, or None if no match — so a mismatch skips the field
    instead of failing the whole order create."""
    if not value:
        return None

    def fetch() -> dict[str, str]:
        for f in describe_fields(mapping.SALES_ORDER):
            if f["name"] == mapping.SALES_ORDER_TERRITORY:
                return {
                    _norm_picklist(v["value"]): v["value"]
                    for v in f["picklistValues"]
                    if v.get("active", True)
                }
        return {}

    return _cached("order_territory_picklist", fetch).get(_norm_picklist(value))


def campaign_id_for(campaign_value: str | None) -> str | None:
    """Resolve our order campaign value to a Campaign record id. Only the
    'rep-non-show' option maps to a campaign ('Rep - Non Show Orders'); anything
    else returns None (Campaign left empty)."""
    if campaign_value != "rep-non-show":
        return None

    def fetch() -> str | None:
        rows = query_all(
            f"SELECT Id FROM Campaign WHERE Name = '{soql_str(mapping.CAMPAIGN_REP_NON_SHOW_NAME)}' LIMIT 1"
        )
        return rows[0]["Id"] if rows else None

    return _cached("campaign:rep-non-show", fetch)


def create_sales_order(header: dict[str, Any], lines: list[dict[str, Any]]) -> tuple[str, str | None]:
    """Create a Kugamon sales order (header + lines) as a Draft.

    Returns (order_id, order_number). Raises on any Salesforce error so Accept
    can surface it — never fail silently on a live-org write. Header is created
    first; each line links back to it. Kugamon auto-numbers Name and sets Status.
    """
    def _create(sobject: str, data: dict[str, Any]) -> dict[str, Any]:
        try:
            return getattr(_client(), sobject).create(data)
        except SalesforceExpiredSession:
            logger.info("Salesforce session expired — re-authenticating")
            _reset_client()
            return getattr(_client(), sobject).create(data)

    # Translate our stored Product2 ids to the Kugamon product-detail ids the
    # line's Product field expects. Do this BEFORE creating the header so a
    # missing mapping doesn't leave an orphan order.
    product2_ids = [line.get(mapping.SALES_ORDER_LINE_PRODUCT) for line in lines]
    detail_by_product = kugamon_detail_ids(product2_ids)
    missing = sorted({p for p in product2_ids if p and p not in detail_by_product})
    if missing:
        raise RuntimeError(f"No Kugamon product detail found for Product2 id(s): {missing}")
    lines = [
        {**line, mapping.SALES_ORDER_LINE_PRODUCT: detail_by_product[line[mapping.SALES_ORDER_LINE_PRODUCT]]}
        for line in lines
    ]

    result = _create(mapping.SALES_ORDER, header)
    if not result.get("success"):
        raise RuntimeError(f"Sales order header rejected: {result.get('errors')}")
    order_id = result["id"]

    for line in lines:
        payload = {**line, mapping.SALES_ORDER_LINE_ORDER: order_id}
        line_result = _create(mapping.SALES_ORDER_LINE, payload)
        if not line_result.get("success"):
            # Header already exists in SF as a Draft — report which line failed.
            raise RuntimeError(
                f"Order {order_id} created, but a line was rejected: {line_result.get('errors')}"
            )

    # Best-effort fetch of the auto-number Name (SO-...) for display.
    number: str | None = None
    try:
        rows = query_all(f"SELECT Name FROM {mapping.SALES_ORDER} WHERE Id = '{soql_str(order_id)}'")
        number = rows[0]["Name"] if rows else None
    except Exception:
        logger.warning("Could not read back the sales order number for %s", order_id)
    return order_id, number


def describe_fields(sobject: str) -> list[dict[str, Any]]:
    """Describe an sobject's fields, re-authenticating once on session expiry."""
    try:
        return getattr(_client(), sobject).describe()["fields"]
    except SalesforceExpiredSession:
        logger.info("Salesforce session expired — re-authenticating")
        _reset_client()
        return getattr(_client(), sobject).describe()["fields"]


def soql_str(value: str) -> str:
    """Escape a string for interpolation into a SOQL literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def soql_like(value: str) -> str:
    """Escape a string for a SOQL LIKE pattern (% and _ are wildcards)."""
    return soql_str(value).replace("%", r"\%").replace("_", r"\_")


def _cached(key: str, fetch: Callable[[], Any]) -> Any:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = fetch()
    _cache[key] = (now + _CACHE_TTL_SECONDS, value)
    return value


# ------------------------------------------------------------------ services

def list_wholesale_pricebooks() -> list[dict[str, Any]]:
    """Active per-season wholesale price books ('F26 Wholesale', ...)."""
    def fetch() -> list[dict[str, Any]]:
        soql = (
            f"SELECT Id, Name FROM {mapping.PRICEBOOK2} "
            f"WHERE IsActive = true AND Name LIKE '%{mapping.WHOLESALE_BOOK_SUFFIX}'"
        )
        return query_all(soql)

    return _cached("pricebooks", fetch)


def get_pricebook_entries(pricebook_id: str) -> list[dict[str, Any]]:
    """Active entries (with product name) for one price book."""
    def fetch() -> list[dict[str, Any]]:
        soql = (
            "SELECT Product2Id, ProductCode, UnitPrice, Product2.Name "
            f"FROM {mapping.PRICEBOOK_ENTRY} "
            f"WHERE Pricebook2Id = '{soql_str(pricebook_id)}' "
            "AND IsActive = true AND Product2.IsActive = true"
        )
        return query_all(soql)

    return _cached(f"entries:{pricebook_id}", fetch)


def list_reps() -> list[str]:
    """Active sales reps = active values of the Account.Salesperson__c picklist."""
    def fetch() -> list[str]:
        for field in describe_fields(mapping.ACCOUNT):
            if field["name"] == mapping.SALESPERSON:
                return sorted(
                    v["label"]
                    for v in field["picklistValues"]
                    if v.get("active", True)
                )
        return []

    return _cached("reps", fetch)


def list_territories() -> list[str]:
    """Distinct Account.SalesTerritory__c values in use, sorted.

    The field is free text, so there is no picklist to read — the option list
    is whatever is actually stored on accounts.
    """
    def fetch() -> list[str]:
        soql = (
            f"SELECT {mapping.SALES_TERRITORY} FROM {mapping.ACCOUNT} "
            f"WHERE {mapping.SALES_TERRITORY} != null "
            f"GROUP BY {mapping.SALES_TERRITORY}"
        )
        values = {
            (r.get(mapping.SALES_TERRITORY) or "").strip()
            for r in query_all(soql)
        }
        return sorted(v for v in values if v)

    return _cached("territories", fetch)


def list_order_writers() -> list[str]:
    """Active values of the sales order's Written_By__c picklist, in picklist order."""
    def fetch() -> list[str]:
        for field in describe_fields(mapping.SALES_ORDER):
            if field["name"] == mapping.WRITTEN_BY:
                return [
                    v["label"]
                    for v in field["picklistValues"]
                    if v.get("active", True)
                ]
        return []

    return _cached("order_writers", fetch)


def list_geocoded_wholesale_accounts() -> list[dict[str, Any]]:
    """Conflict-check candidate set: wholesale accounts with shipping geocodes,
    at least one sales order in the last CONFLICT_ORDER_YEARS years, and a
    Rank__c outside EXCLUDED_RANKS (inactive / no-booking / conflict / OOB).

    The order-history filter (decision 2026-07-17) keeps only active
    stockists — it also drops all "(CLOSED)"-named accounts, which have no
    recent orders. Verified against the org: 4,395 -> 897 -> 824 candidates
    after the rank exclusion (decision 2026-07-18).
    """
    def fetch() -> list[dict[str, Any]]:
        since = date.today() - timedelta(days=365 * settings.conflict_order_years)
        fields = ", ".join(mapping.NEARBY_ACCOUNT_FIELDS)
        excluded_ranks = ", ".join(f"'{soql_str(r)}'" for r in mapping.EXCLUDED_RANKS)
        soql = (
            f"SELECT {fields} FROM {mapping.ACCOUNT} "
            f"WHERE {mapping.ACCOUNT_TYPE} = '{mapping.WHOLESALE_TYPE}' "
            f"AND {mapping.SHIPPING_LAT} != null "
            f"AND {mapping.SHIPPING_LNG} != null "
            f"AND ({mapping.RANK} = null OR {mapping.RANK} NOT IN ({excluded_ranks})) "
            f"AND Id IN (SELECT {mapping.SALES_ORDER_ACCOUNT} FROM {mapping.SALES_ORDER} "
            f"WHERE {mapping.SALES_ORDER_DATE} >= {since.isoformat()})"
        )
        accounts = query_all(soql)

        # Most recent order per candidate — both its date and its Name. A
        # GROUP BY MAX(date) can't also return the Name of that row, so pull
        # the orders newest-first and keep the first one seen per account.
        # ORDER BY holds across queryMore pagination, so "first seen = latest".
        # Field aliasing is only allowed in aggregate queries, so read the
        # real field names back off each row.
        recent = query_all(
            f"SELECT {mapping.SALES_ORDER_ACCOUNT}, Name, {mapping.SALES_ORDER_NAME}, "
            f"{mapping.SALES_ORDER_DATE} "
            f"FROM {mapping.SALES_ORDER} "
            f"WHERE {mapping.SALES_ORDER_DATE} >= {since.isoformat()} "
            f"ORDER BY {mapping.SALES_ORDER_DATE} DESC"
        )
        last_by_account: dict[str, dict[str, Any]] = {}
        for r in recent:
            last_by_account.setdefault(
                r[mapping.SALES_ORDER_ACCOUNT],
                {
                    "date": r[mapping.SALES_ORDER_DATE],
                    "number": r.get("Name"),
                    "name": r.get(mapping.SALES_ORDER_NAME),
                },
            )
        for a in accounts:
            latest = last_by_account.get(a["Id"])
            a["lastOrderDate"] = latest["date"] if latest else None
            a["lastOrderNumber"] = latest["number"] if latest else None
            a["lastOrderName"] = latest["name"] if latest else None
        return accounts

    return _cached("geocoded_accounts", fetch)


def find_accounts(
    email: str | None = None,
    account_id: str | None = None,
    name: str | None = None,
) -> list[dict[str, Any]]:
    """Buyer lookup on Account (person-account org). Returns all candidates.

    Name matching is an EXACT match on the whole account name (store name),
    not a substring — SOQL `=` on text is case-insensitive, so casing is
    forgiven but partial words are not. Identical names still return every
    candidate so the frontend can show the "which one?" dropdown, same as email.
    """
    fields = ", ".join(mapping.ACCOUNT_FIELDS)
    if email:
        where = f"{mapping.ACCOUNT_LOOKUP_EMAIL} = '{soql_str(email)}'"
    elif account_id:
        where = f"Id = '{soql_str(account_id)}'"
    elif name:
        where = f"Name = '{soql_str(name.strip())}'"
    else:
        raise ValueError("email, account_id or name required")
    # Drop inactive / no-booking / conflict / OOB accounts from the buyer
    # lookup — same EXCLUDED_RANKS gate as the conflict-check candidate set
    # (decision 2026-07-18). Accounts with no rank still match.
    excluded_ranks = ", ".join(f"'{soql_str(r)}'" for r in mapping.EXCLUDED_RANKS_FIND_ACCOUNT)
    rank_filter = f"({mapping.RANK} = null OR {mapping.RANK} NOT IN ({excluded_ranks}))"
    # IsPersonAccount = FALSE keeps only business accounts. This IS a
    # person-account org, but wholesale stockists are business accounts
    # (verified against the org: 4,477 of 4,484 Type='Wholesale' accounts);
    # the filter drops DTC / consumer person accounts from the buyer lookup.
    soql = (
        f"SELECT {fields} FROM {mapping.ACCOUNT} "
        f"WHERE ({where}) AND {rank_filter} AND IsPersonAccount = FALSE "
        f"ORDER BY Name LIMIT 25"
    )
    return query_all(soql)
