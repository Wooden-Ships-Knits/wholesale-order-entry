"""Run the Salesforce "Rep Open Order Detail Report" and return its lines.

The report is the source of truth for WHICH orders are open (its filters:
not released/cancelled, no samples, no retail, no projections, …), so this
runs the report itself through the Analytics API rather than re-creating those
filters in SOQL — edit the report in Salesforce and this follows.

Two things the API needs handled:

- The saved "Order Date <= <date>" filter is stale (someone updates it on the
  run page). It is replaced with today here, in the metadata sent with the run.
- A synchronous run returns at most 2,000 detail rows and the report has far
  more. Each run is limited to an order-date range, and a range that comes back
  incomplete (allData = False) is split in half and re-run. Every line of an
  order shares its order date, so an order is never split across two runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.config import settings
from app.salesforce.client import _client, soql_str

ORDER_DATE = "kugo2p__SalesOrder__c.kugo2p__OrderDate__c"
# The report's grouping: the ORDER's own Sales Territory. Not a detail column,
# so it's taken from the grouping each row sits under and stored under this
# key. It is what the team's files show as "Sales Territory" — NOT the report's
# "Current Sales Territory" column, which follows the account and moves when an
# account is reassigned (checked on all 874 orders of the 2026-10-26 file).
SALES_TERRITORY = "kugo2p__SalesOrder__c.kugo2p__SalesTerritory__c"
# The report already filters Order Date > 2011-01-01; nothing older exists.
EARLIEST = date(2011, 1, 2)


@dataclass
class Report:
    rows: list[dict[str, Any]]  # one per order line: {api column -> value, SALES_TERRITORY -> label}
    expected_rows: int  # the report's RowCount for the same filters
    runs: int  # how many API runs it took


def _report_id(sf) -> str:
    rows = sf.query(f"SELECT Id FROM Report WHERE Name = '{soql_str(settings.oo_report_name)}'")["records"]
    if not rows:
        raise RuntimeError(f"Salesforce report {settings.oo_report_name!r} not found")
    return rows[0]["Id"]


def _metadata(sf, report_id: str, today: date) -> tuple[dict, dict[str, str]]:
    """The report's own metadata, with its Order Date upper bound set to today,
    and each detail column's data type."""
    described = sf.restful(f"analytics/reports/{report_id}/describe")
    md = described["reportMetadata"]
    types = {
        col: info.get("dataType", "string")
        for col, info in described["reportExtendedMetadata"]["detailColumnInfo"].items()
    }
    filters = md.get("reportFilters") or []
    upper = [f for f in filters if f["column"] == ORDER_DATE and f["operator"] == "lessOrEqual"]
    for f in upper:
        f["value"] = today.isoformat()
    if not upper:
        filters.append({"column": ORDER_DATE, "operator": "lessOrEqual", "value": today.isoformat()})
    md["reportFilters"] = filters
    return md, types


def _run(sf, report_id: str, md: dict, details: bool) -> dict:
    return sf.restful(
        f"analytics/reports/{report_id}",
        method="POST",
        json={"reportMetadata": md},
        params={"includeDetails": "true" if details else "false"},
    )


def _with_range(md: dict, start: date, end: date) -> dict:
    sliced = dict(md)
    sliced["reportFilters"] = md["reportFilters"] + [
        {"column": ORDER_DATE, "operator": "greaterOrEqual", "value": start.isoformat()},
        {"column": ORDER_DATE, "operator": "lessOrEqual", "value": end.isoformat()},
    ]
    return sliced


def _cell(cell: dict, data_type: str = "string") -> Any:
    """A detail cell's usable value, by the column's report data type: the raw
    value for dates ('2026-06-11', not the display '6/11/2026') and numbers,
    the display label for text, picklists and lookups (a lookup's value is a
    record id)."""
    value = cell.get("value")
    if value is None:
        return None
    if isinstance(value, dict):  # currency: {"amount": 70.0, "currency": "USD"}
        return value.get("amount")
    if data_type in ("date", "datetime") or isinstance(value, (int, float)):
        return value
    label = cell.get("label")
    return value if label is None else label


def fetch(today: date) -> Report:
    sf = _client()
    report_id = _report_id(sf)
    md, types = _metadata(sf, report_id, today)
    columns = md["detailColumns"]

    # Totals-only run: the row count the detail runs must add up to.
    summary = _run(sf, report_id, md, details=False)
    row_count_at = md["aggregates"].index("RowCount")
    expected = int(summary["factMap"]["T!T"]["aggregates"][row_count_at]["value"] or 0)

    rows: list[dict[str, Any]] = []
    runs = 1
    pending = [(EARLIEST, today)]
    while pending:
        start, end = pending.pop()
        result = _run(sf, report_id, _with_range(md, start, end), details=True)
        runs += 1
        if not result.get("allData", True):
            if start >= end:
                raise RuntimeError(f"More than 2,000 open-order lines dated {start} — cannot split further")
            mid = start + timedelta(days=(end - start).days // 2)
            pending += [(start, mid), (mid + timedelta(days=1), end)]
            continue
        for g in result["groupingsDown"]["groupings"]:
            fact = result["factMap"].get(f"{g['key']}!T") or {}
            # A grouping with no value is labelled "-" by the API.
            territory = g["label"] if g.get("value") not in (None, "") else ""
            for detail in fact.get("rows", []):
                row = {col: _cell(c, types.get(col, "string")) for col, c in zip(columns, detail["dataCells"])}
                row[SALES_TERRITORY] = territory
                rows.append(row)

    return Report(rows=rows, expected_rows=expected, runs=runs)
