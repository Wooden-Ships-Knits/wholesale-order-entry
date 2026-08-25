"""Fill `top_brands` on rows already assessed, from the page cache.

WHY THIS IS NOT A RE-JUDGE. `top_brands` is a measurement, not an answer: it
comes out of the scraped catalogue with no model involved. So a row that was
already judged can gain the column for the price of a cache read -- no model
call, no verdict touched, nothing re-decided. A full re-judge costs ~35 minutes
and hands back a fresh set of model answers; this costs neither.

    docker compose ... exec backend python -m app.prospects.backfill_brands
    docker compose ... exec backend python -m app.prospects.backfill_brands --overwrite

Only rows whose `top_brands` is empty are touched unless --overwrite is given.
Safe to stop and re-run: it commits in batches and picks up where it left off.
"""
import argparse
import logging

from sqlalchemy import select

from app.db.models import Prospect

from . import assess
from .analysis.llm_payload import store_payload

logger = logging.getLogger(__name__)
BATCH = 50


def pending(db, overwrite=False):
    """Assessed rows with a website whose shelf is not recorded yet."""
    q = select(Prospect).where(Prospect.website.isnot(None), Prospect.website != "",
                               Prospect.assessed_at.isnot(None))
    if not overwrite:
        q = q.where(Prospect.top_brands.is_(None))
    return db.execute(q.order_by(Prospect.store_name)).scalars().all()


def run(db, overwrite=False) -> int:
    pattern = assess.load_pattern()
    signature = assess.tag_signature(pattern)
    rows = pending(db, overwrite)
    print(f"{len(rows)} row(s) to fill", flush=True)

    filled = missed = 0
    for i, p in enumerate(rows, 1):
        try:
            store = assess._scrape(p.website)
            payload = store_payload(store.get("domain") or "", store,
                                    store.get("about_text"), signature)
        except Exception:
            # A shop whose pages were never cached, or whose website is not a
            # hostname. Not worth stopping for: the column stays NULL, which
            # reads as "not recorded" rather than "stocks no brands".
            missed += 1
            continue
        p.top_brands = "; ".join(payload.get("top_brands") or []) or None
        filled += 1
        if i % BATCH == 0:
            db.commit()
            print(f"  {i}/{len(rows)}", flush=True)
    db.commit()
    print(f"filled {filled}, could not read {missed}", flush=True)
    return filled


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--overwrite", action="store_true",
                    help="refresh rows that already have a shelf recorded")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        run(db, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
