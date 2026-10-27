"""The reports' "today" is Bali time, not the server's."""
from datetime import datetime, timezone
from unittest import mock

from app.reports import clock


def test_today_is_bali_time_not_jakarta():
    # 16:30 UTC = 23:30 in Jakarta (UTC+7) but already 00:30 the next day in Bali (UTC+8).
    fixed = datetime(2026, 10, 27, 16, 30, tzinfo=timezone.utc)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz)

    with mock.patch.object(clock, "datetime", FakeDatetime):
        assert str(clock.today()) == "2026-10-28"
