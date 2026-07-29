"""Salesforce side of the DMM report — the unpaid open orders table."""
import pandas as pd

from app.config import settings
from app.salesforce.client import _client


def report() -> pd.DataFrame:
    """Reproduce the UNPAID DAILY MORNING MEETING report as shown in the SF UI.

    The report is a TABULAR report (no groupings): every detail row is a single
    SO. factMap['T!T']['rows'] holds the detail rows, and each dataCell carries
    a formatted display string ('label') plus the raw value ('value'). We keep
    the formatted labels so the DataFrame matches the SF UI one-to-one (e.g.
    '$1,068.00', '16.0000'); text_gen parses them back where it needs numbers.
    """
    sf = _client()  # shared, already-authenticated session
    rpt = sf.query(f"SELECT Id FROM Report WHERE Name = '{settings.dmm_report_name}'")
    records = rpt["records"]
    if not records:
        raise RuntimeError(f"No Salesforce report named {settings.dmm_report_name!r}")
    result = sf.restful(f"analytics/reports/{records[0]['Id']}")

    cols = result["reportMetadata"]["detailColumns"]  # column API names, in display order
    info = result["reportExtendedMetadata"]["detailColumnInfo"]
    labels = [info[c]["label"] for c in cols]  # ['Product Amount', 'Order: Order Number', ...]

    rows = [
        {lbl: cell["label"] for lbl, cell in zip(labels, r["dataCells"])}
        for r in result["factMap"]["T!T"]["rows"]
    ]
    return pd.DataFrame(rows, columns=labels)
