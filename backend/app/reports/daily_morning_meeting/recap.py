"""DMM entry point for /api/admin/reports/dmm — same contract as the DTO recap.

The standalone script wrote Output/report.txt; here run() returns the text so
the admin page can hold the last run in memory and re-show it without
re-running (routers/reports.py).
"""
from app.config import settings

from . import text_gen


def run() -> dict:
    """Build the DMM recap. Returns {"recap": str, "log": [str, ...]}."""
    log = [
        f"Salesforce report: {settings.dmm_report_name!r}.",
        "Sheets: 'WHOLESALE Paid Open Orders' + 'Email Schedule'.",
    ]
    text, paid_sos, unpaid_groups = text_gen.genText()
    log.append(f"Paid SOs updated today (sheet): {paid_sos}.")
    log.append(f"Unpaid groups (Salesforce report): {unpaid_groups}.")
    if not unpaid_groups:
        log.append(
            "The Salesforce report returned no rows — check its saved date "
            "filter; the API ignores anything widened on the run page."
        )
    log.append(f"Recap built ({len(text.splitlines())} lines).")
    return {"recap": text.strip(), "log": log}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
