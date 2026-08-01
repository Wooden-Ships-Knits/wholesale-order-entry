"""/api/admin/notices — payment-notice product cards.

POST /notices/run builds one card per SO number. Photos are streamed from the
shared drive as they are drawn — a card opens a handful of images out of the
~250 in a season, so nothing is mirrored to disk and the VM stores only the
finished cards.

Like the original main.py, each run clears the output folder first: the Cards
list then always shows exactly what this run produced.
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.admin.security import AdminRequired
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/notices")

# Salesforce SO names look like SO-260720-0073265.
_SO_RE = re.compile(r"^[A-Za-z0-9\-]{3,40}$")


class RunRequest(BaseModel):
    season_code: str = Field(pattern=r"^[FS]\d{2}$")
    so_numbers: list[str] = Field(min_length=1, max_length=50)


def _card_dir() -> Path:
    return Path(settings.notice_output_dir)


@router.post("/run", dependencies=[AdminRequired])
def run_cards(payload: RunRequest) -> dict:
    """Build one card per SO number, streaming photos from Drive as needed."""
    bad = [s for s in payload.so_numbers if not _SO_RE.match(s.strip())]
    if bad:
        raise HTTPException(status_code=422, detail=f"Not valid SO numbers: {bad[:3]}")

    # Imported here, not at module import: matplotlib and the card builder are
    # heavy, and nothing else in the app needs them.
    from app.notices.number_5 import SO_order

    # The card builder reads the season from a module global (it was a script
    # driven by varia.py). Setting it per request is the least invasive way to
    # make it season-agnostic without rewriting the drawing code.
    SO_order.season_code = payload.season_code

    # Start clean, as the standalone main.py did, so "Cards" only ever lists
    # this run's output and old cards can't accumulate on the VM.
    out = _card_dir()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*card.png"):
        old.unlink()
        logger.info("Cleared old card %s", old.name)

    log: list[str] = []
    cards: list[str] = []
    for so in [s.strip() for s in payload.so_numbers]:
        try:
            SO_order.item_fetch(so)
            name = f"{SO_order.safe_filename(so)} card.png"
            if (_card_dir() / name).exists():
                cards.append(name)
                log.append(f"{so}: card generated")
            else:
                log.append(f"{so}: finished but no card file was written")
        except Exception as exc:
            logger.exception("Card generation failed for %s", so)
            log.append(f"{so}: FAILED — {exc}")

    return {"ran": True, "ranAt": datetime.now(timezone.utc).isoformat(),
            "cards": cards, "log": log}


@router.get("/cards", dependencies=[AdminRequired])
def list_cards() -> dict:
    """Cards currently on disk, newest first."""
    d = _card_dir()
    if not d.is_dir():
        return {"cards": []}
    files = sorted((p for p in d.glob("*card.png") if p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return {"cards": [{"name": p.name, "size": p.stat().st_size} for p in files]}


@router.get("/cards/{name}", dependencies=[AdminRequired])
def get_card(name: str) -> FileResponse:
    """Stream one card. Resolved and re-checked against the output directory so
    a crafted name can't walk out of it (same guard as the order PDFs)."""
    base = _card_dir().resolve()
    path = (base / name).resolve()
    if not str(path).startswith(str(base) + "/") or not path.is_file():
        raise HTTPException(status_code=404, detail="Card not found")
    return FileResponse(path, media_type="image/png", filename=path.name)
