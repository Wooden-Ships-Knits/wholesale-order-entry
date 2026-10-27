"""/api/admin/reports — run the DTO/DMM/OO automation reports.

Option A caching: the last run of each report is held in a module-level dict so
the admin page can re-show it without re-running. It survives page reloads but
is cleared when the backend restarts (a fresh run rebuilds it).

A runner may also return "file": (filename, bytes) — OO's zip of .xlsx files. The bytes are
kept beside the cached run and served by GET /{key}/file; the JSON only says a
download exists.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response

from app.admin.security import AdminRequired
from app.reports.daily_morning_meeting import recap as dmm
from app.reports.daily_total_order import recap as dto
from app.reports.open_order import recap as oo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reports")

# report key -> its run() function, each returning {"recap": str, "log": [...]}.
_RUNNERS = {
    "dto": dto.run,
    "dmm": dmm.run,
    "oo": oo.run,
}

# report key -> last run: {"ran": True, "recap": str, "log": [...], "ranAt": iso}
_last_run: dict[str, dict] = {}
# report key -> (filename, bytes) of the last run's file, for reports that make one.
_last_file: dict[str, tuple[str, bytes]] = {}


@router.get("/{key}", dependencies=[AdminRequired])
def last_run(key: str) -> dict:
    """The last cached run for this report, or {"ran": False} if never run."""
    if key not in _RUNNERS:
        raise HTTPException(status_code=404, detail="Unknown report")
    return _last_run.get(key) or {"ran": False}


@router.post("/{key}/run", dependencies=[AdminRequired])
def run_report(key: str) -> dict:
    """Run the report now (slow — hits Salesforce), cache it, and return it."""
    runner = _RUNNERS.get(key)
    if runner is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    try:
        out = runner()
    except Exception as exc:  # surfaced to the admin; don't cache a failure
        logger.exception("Report %s failed", key)
        raise HTTPException(status_code=502, detail=f"Report failed: {exc}")

    file = out.pop("file", None)
    result = {"ran": True, "ranAt": datetime.now(timezone.utc).isoformat(), **out}
    if file:
        _last_file[key] = file
        result["download"] = file[0]
    _last_run[key] = result
    return result


_MEDIA_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}


@router.get("/{key}/file", dependencies=[AdminRequired])
def last_file(key: str) -> Response:
    """The file from the last run (e.g. OO's zip), as a download."""
    if key not in _RUNNERS:
        raise HTTPException(status_code=404, detail="Unknown report")
    file = _last_file.get(key)
    if file is None:
        raise HTTPException(status_code=404, detail="No file yet — run the report first")
    name, data = file
    return Response(
        content=data,
        media_type=_MEDIA_TYPES.get(name[name.rfind("."):].lower(), "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
