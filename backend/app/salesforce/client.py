"""Salesforce client: session management, SOQL helpers, query services.

All calls happen backend-side only. Credentials come from settings (.env).
The session is created lazily and re-created automatically on expiry.
"""
import logging
import threading
import time
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


def soql_str(value: str) -> str:
    """Escape a string for interpolation into a SOQL literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


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


def find_accounts(email: str | None = None, account_id: str | None = None) -> list[dict[str, Any]]:
    """Buyer lookup on Account (person-account org). Returns all candidates."""
    fields = ", ".join(mapping.ACCOUNT_FIELDS)
    if email:
        where = f"{mapping.ACCOUNT_LOOKUP_EMAIL} = '{soql_str(email)}'"
    elif account_id:
        where = f"Id = '{soql_str(account_id)}'"
    else:
        raise ValueError("email or account_id required")
    soql = f"SELECT {fields} FROM {mapping.ACCOUNT} WHERE {where}"
    return query_all(soql)
