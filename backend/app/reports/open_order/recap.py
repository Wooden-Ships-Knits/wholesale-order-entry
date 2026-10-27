"""OO (Open Order) entry point for /api/admin/reports/oo — same contract as the
DTO/DMM recaps, plus the files under "file" (routers/reports.py keeps them for
download and leaves them out of the JSON).

The download is one zip: the Master file (every order) and one file per rep
plus House (rep_files.py).
"""
from __future__ import annotations

import io
import zipfile
from app.config import settings
from app.reports.clock import today

from . import fetch, rep_files, workbook

LEGEND = {
    "yellow": "YELLOW - orders we entered last week. Make sure nothing is missing!",
    "orange": "ORANGE - orders within the ship window. See the Problem List in case they are stuck.",
    "red": "RED - orders PAST the ship window. See the Problem List Email for details",
}


def run() -> dict:
    """Build the OO files. Returns {"recap", "log", "file": (zip name, bytes)}."""
    day = today()
    log = [
        f"Salesforce report: {settings.oo_report_name!r}, order date up to {day:%Y-%m-%d} ({settings.report_timezone}).",
    ]
    report = fetch.fetch(day)
    log.append(f"Fetched {len(report.rows)} order lines in {report.runs} API runs.")
    # The split runs must add up to the report's own count, or a slice was lost.
    if len(report.rows) != report.expected_rows:
        raise RuntimeError(
            f"Fetched {len(report.rows)} lines but the report counts {report.expected_rows} — "
            "not writing an incomplete file. Run it again."
        )
    log.append(f"Matches the report's own row count ({report.expected_rows}).")

    orders = workbook.group_orders(report.rows, day)
    # Before writing anything: an uncovered territory or rep stops the run here.
    books = rep_files.split_orders(orders)

    stamp = f"{day:%y%m%d}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"Master - OO-YTD-{stamp}.xlsx", workbook.build(orders))
        for rep_file, sheets in books:
            z.writestr(rep_file.filename(day), workbook.build_book(sheets))
    data = buf.getvalue()
    name = f"OO-YTD-{stamp}.zip"
    log.append(
        f"Built {name}: Master ({len(orders)} orders) + {len(books)} rep/House files, {len(data) // 1024} KB."
    )

    counts = {c: [o for o in orders if o.colour == c] for c in LEGEND}
    lines = [f"Open orders as of {day:%b %-d, %Y}: {len(orders)} orders, "
             f"{sum(o.qty for o in orders):,.0f} pcs, ${sum(o.amount for o in orders):,.0f}.", ""]
    for colour, text in LEGEND.items():
        lines.append(f"• {text} — {len(counts[colour])} orders")
    lines += ["", "Files:"]
    for rep_file, sheets in books:
        own = sum(len(sh.own) for sh in sheets)
        split = sum(len(sh.split) for sh in sheets)
        lines.append(
            f"  {rep_file.filename(day)} — {own} order{'' if own == 1 else 's'}"
            + (f" + {split} split" if split else "")
        )
    if counts["red"]:
        lines += ["", "Past the ship window:"]
        for o in sorted(counts["red"], key=lambda o: str(o.first.get(workbook.THRU) or "")):
            lines.append(
                f"  {o.number}  {o.first.get(workbook.ACCOUNT) or '—'}  "
                f"(ship thru {o.first.get(workbook.THRU) or '—'}, {o.first.get(workbook.TERRITORY) or '—'})"
            )
    return {"recap": "\n".join(lines), "log": log, "file": (name, data)}


if __name__ == "__main__":
    import json

    out = run()
    out.pop("file")
    print(json.dumps(out, indent=2))
