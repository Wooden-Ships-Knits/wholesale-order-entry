"""/api/admin/reports — run the DTO/DMM automation reports.

Option A caching: the last run of each report is held in a module-level dict so
the admin page can re-show it without re-running. It survives page reloads but
is cleared when the backend restarts (a fresh run rebuilds it).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.admin.security import AdminRequired
from app.reports.daily_total_order import recap as dto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reports")

# report key -> its run() function. Add "dmm" here once that report is ported.
_RUNNERS = {
    "dto": dto.run,
}

# report key -> last run: {"ran": True, "recap": str, "log": [...], "ranAt": iso}
_last_run: dict[str, dict] = {}


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

    result = {"ran": True, "ranAt": datetime.now(timezone.utc).isoformat(), **out}
    _last_run[key] = result
    return result
