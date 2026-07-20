"""Salesforce client: session management, SOQL helpers, query services.

All calls happen backend-side only. Credentials come from settings (.env).
The session is created lazily and re-created automatically on expiry.
"""
import logging
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
    soql = f"SELECT {fields} FROM {mapping.ACCOUNT} WHERE {where} ORDER BY Name LIMIT 25"
    return query_all(soql)
