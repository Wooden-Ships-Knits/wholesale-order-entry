"""Salesforce side of the DMM report — the unpaid open orders, and order details
the report doesn't carry (account, territory, AIR/FCL)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from app.config import settings
from app.salesforce import mapping
from app.salesforce.client import _client, query_all, soql_str

logger = logging.getLogger(__name__)

DATE_REQUIRED = "kugo2p__SalesOrder__c.kugo2p__DateRequired__c"
ORDER_NO = "CUST_NAME"
AMOUNT = "kugo2p__SalesOrder__c.kugo2p__ProductAmount__c"
SHIPMENT = "kugo2p__SalesOrder__c.Estimated_Shipment_Name__c"
UNITS = "kugo2p__SalesOrder__c.Total_Units__c"
ORDER_NAME = "kugo2p__SalesOrder__c.kugo2p__OrderName__c"


@dataclass
class Unpaid:
    number: str
    shipment: str  # Estimated Shipment Name, e.g. '10-01 AIR'
    order_name: str  # e.g. 'F26 SWEATERS 10/01 - 10/30'
    units: float
    amount: float


def window_end(today: date) -> date:
    """Last day of next month: the unpaid windows the meeting covers. In the
    26 Oct 2026 recap that meant every window up to November."""
    first_after = date(today.year + (today.month + 1) // 12, (today.month + 1) % 12 + 1, 1)
    return first_after - timedelta(days=1)


def report(today: date) -> list[Unpaid]:
    """Run the UNPAID DAILY MORNING MEETING report (tabular: one row per SO).

    The report's saved "Date Required <= …" filter was edited by hand on the
    run page, which the API never sees — on 2026-09-22 and again on 2026-10-27
    it still read 2026-07-01 and the report returned nothing. The upper bound
    is set here on every run instead (window_end), as the OO report does.
    """
    sf = _client()
    found = sf.query(f"SELECT Id FROM Report WHERE Name = '{soql_str(settings.dmm_report_name)}'")["records"]
    if not found:
        raise RuntimeError(f"No Salesforce report named {settings.dmm_report_name!r}")
    report_id = found[0]["Id"]

    md = sf.restful(f"analytics/reports/{report_id}/describe")["reportMetadata"]
    filters = md.get("reportFilters") or []
    upper = [f for f in filters if f["column"] == DATE_REQUIRED and f["operator"] == "lessOrEqual"]
    for f in upper:
        f["value"] = window_end(today).isoformat()
    if not upper:
        filters.append({"column": DATE_REQUIRED, "operator": "lessOrEqual", "value": window_end(today).isoformat()})
    md["reportFilters"] = filters

    result = sf.restful(f"analytics/reports/{report_id}", method="POST", json={"reportMetadata": md})
    if not result.get("allData", True):
        raise RuntimeError("The unpaid report has more than 2,000 rows — the API returned only part of it")

    cols = md["detailColumns"]
    rows = []
    for r in result["factMap"]["T!T"]["rows"]:
        cell = dict(zip(cols, r["dataCells"]))
        amount = cell[AMOUNT]["value"]
        rows.append(Unpaid(
            number=cell[ORDER_NO]["label"],
            shipment=cell[SHIPMENT]["label"] or "",
            order_name=cell[ORDER_NAME]["label"] or "",
            units=float(cell[UNITS]["value"] or 0),
            amount=float((amount or {}).get("amount") or 0) if isinstance(amount, dict) else float(amount or 0),
        ))
    return rows


@dataclass
class OrderInfo:
    account: str
    territory: str  # the order's Sales Territory, e.g. 'FL - Jason Hilsenrad'
    shipment: str  # Estimated Shipment Name


def orders(numbers: list[str]) -> dict[str, OrderInfo]:
    """{SO number: OrderInfo} for these orders; numbers not found are left out."""
    account = mapping.SALES_ORDER_ACCOUNT.removesuffix("__c") + "__r"
    out: dict[str, OrderInfo] = {}
    unique = sorted(set(numbers))
    for i in range(0, len(unique), 200):
        inlist = "','".join(soql_str(n) for n in unique[i:i + 200])
        for r in query_all(
            f"SELECT Name, {account}.Name, {mapping.SALES_ORDER_TERRITORY}, {mapping.ESTIMATED_SHIPMENT_NAME} "
            f"FROM {mapping.SALES_ORDER} WHERE Name IN ('{inlist}')"
        ):
            out[r["Name"]] = OrderInfo(
                account=(r.get(account) or {}).get("Name") or "",
                territory=r.get(mapping.SALES_ORDER_TERRITORY) or "",
                shipment=r.get(mapping.ESTIMATED_SHIPMENT_NAME) or "",
            )
    return out


def mode(shipment: str) -> str | None:
    """'AIR' / 'FCL' from an Estimated Shipment Name like '06-05 FCL'."""
    last = shipment.split()[-1].upper() if shipment.split() else ""
    return last if last in ("AIR", "FCL") else None
