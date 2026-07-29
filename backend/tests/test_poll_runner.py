"""The scheduled entrypoint (cron target) that runs capture + classify once."""
from unittest.mock import MagicMock, patch

from app.tasks import poll_replies


def test_run_once_polls_then_classifies_and_returns_counts():
    with patch("app.tasks.poll_replies.SessionLocal", return_value=MagicMock()) as SL, patch(
        "app.tasks.poll_replies.inbound.run_poll", return_value=3
    ) as poll, patch(
        "app.tasks.poll_replies.conflict_reply.run_classify", return_value=2
    ) as classify:
        result = poll_replies.run_once()
    assert result == {"captured": 3, "suggested": 2}
    poll.assert_called_once()
    classify.assert_called_once()
    # the session it opened is always closed
    SL.return_value.close.assert_called_once()
