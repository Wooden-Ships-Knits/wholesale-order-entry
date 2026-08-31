"""Assess a whole book, one territory at a time.

WHY NOT JUST `assess_pending(db)`. A whole-book run is ~1,300 shops and about
seven hours of scraping. `pending()` orders by store_name, so that run leaves
all twelve territories half-assessed until the very end — and a seven-hour run
WILL be interrupted: a laptop sleeps, a session is killed, somebody needs the
machine. Territory by territory, every interruption leaves finished books
behind instead of twelve unusable halves.

    docker compose ... exec backend python -m app.prospects.batch
    docker compose ... exec backend python -m app.prospects.batch --lead "CA/HI - Rande Cohen"
    docker compose ... exec backend python -m app.prospects.batch --territory "FL - Jason Hilsenrad"

Re-running is always safe: `pending()` skips anything with `assessed_at`, so an
interrupted run resumes where it stopped and a finished one is a no-op.
"""
import argparse
import logging
import time

from sqlalchemy import func, select

from app.db.models import Prospect

from . import assess

logger = logging.getLogger(__name__)


def pending_by_territory(db) -> dict:
    """{territory: how many shops still need assessing}."""
    rows = db.execute(
        select(Prospect.territory, func.count())
        .where(Prospect.website.isnot(None), Prospect.website != "",
               Prospect.assessed_at.is_(None))
        .group_by(Prospect.territory)
    ).all()
    return {t: n for t, n in rows if t}


def order_territories(counts: dict, lead: str | None = None) -> list:
    """Which book to finish first.

    `lead` goes first when it has work — normally whichever territory is being
    tested against, so its book is whole before the long tail is touched. The
    rest run biggest-first: the largest book is the one most likely to be cut
    short, so it gets the most runway.
    """
    todo = {t: n for t, n in counts.items() if n}
    rest = sorted((t for t in todo if t != lead),
                  key=lambda t: (-todo[t], t))
    return ([lead] if lead in todo else []) + rest


def run(db, lead: str | None = None, only: str | None = None) -> int:
    """Assess everything pending. Returns how many rows were written."""
    counts = pending_by_territory(db)
    order = [only] if only else order_territories(counts, lead)

    total = sum(counts.get(t, 0) for t in order)
    print(f"{total} shop(s) pending across {len(order)} territory(ies)", flush=True)

    written = 0
    for i, territory in enumerate(order, 1):
        started = time.monotonic()
        print(f"\n=== [{i}/{len(order)}] {territory} "
              f"({counts.get(territory, 0)} pending) ===", flush=True)
        try:
            n = assess.assess_pending(db, territory=territory)
        except Exception:
            # Every row already written cost a scrape and a model call. One bad
            # territory must not throw away the books queued behind it.
            logger.exception("territory FAILED: %s", territory)
            continue
        written += n
        print(f"=== DONE {territory}: {n} written in "
              f"{(time.monotonic() - started) / 60:.1f} min "
              f"(running total {written}) ===", flush=True)

    print(f"\n=== ALL WRITTEN: {written} ===", flush=True)
    return written


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lead", help="territory to finish first")
    p.add_argument("--territory", help="run ONLY this territory")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        run(db, lead=args.lead, only=args.territory)


if __name__ == "__main__":
    main()
