"""The reports' "today" — Bali time, whatever timezone the server runs in."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings


def today() -> date:
    return datetime.now(ZoneInfo(settings.report_timezone)).date()
