"""Scheduled entrypoint: capture inbound conflict replies, then classify them.

Run this on a cadence in production (cron on the VM). It is the non-HTTP twin of
the admin "Check replies" button (POST /api/admin/poll-replies) — same two steps,
but callable without an admin session, which suits a cron job:

    */5 * * * *  cd /opt/wholesale-order-entry && \
        docker compose exec -T backend python -m app.tasks.poll_replies

Both steps no-op when IMAP / OpenAI are unconfigured, and captured replies are
deduped by Message-ID, so running it repeatedly is safe.
"""
import logging

from app.ai import conflict_reply
from app.db.session import SessionLocal
from app.email import inbound

logger = logging.getLogger(__name__)


def run_once() -> dict:
    """Poll the mailbox then classify, in one own-session unit of work."""
    db = SessionLocal()
    try:
        captured = inbound.run_poll(db)
        suggested = conflict_reply.run_classify(db)
    finally:
        db.close()
    logger.info("poll_replies: captured=%d suggested=%d", captured, suggested)
    return {"captured": captured, "suggested": suggested}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = run_once()
    print(f"captured={result['captured']} suggested={result['suggested']}")


if __name__ == "__main__":
    main()
