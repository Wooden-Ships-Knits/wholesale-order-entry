"""Read a shop's shelf back out of the page cache — what brands it stocks.

The cache holds raw HTTP bodies (`output-dev/prospects/cache/<domain>/*.json`),
so it cannot be browsed for an answer to "what does this shop sell". That
answer is computed by `store_payload()` at assessment time, and `top_brands` is
NOT persisted -- so the gate that turns on it cannot be audited from the table.
This re-derives it. No network: everything comes from the cache.

    docker compose ... exec backend python -m app.prospects.inspect "Hill House Home"
    docker compose ... exec backend python -m app.prospects.inspect --domain lspace.com

Why it matters: Hill House Home reports 7 brands, and 946 of its 967 products
are its own name -- the other "brands" are category strings misfiled into the
vendor field ("WOMENS APPAREL_NAP DRESS"). `brand_count` alone cannot see that;
this shows it in one screen.
"""
import argparse
from collections import Counter

from sqlalchemy import select

from app.db.models import Prospect

from . import assess
from .analysis.llm_payload import store_payload, unreadable_reason

TOP = 25


def shelf(store):
    """Vendor strings on this shop's shelf, deepest-stocked first."""
    return Counter((p.get("vendor") or "").strip().upper()
                   for p in store["products"] if (p.get("vendor") or "").strip())


def report(db, name=None, domain=None, top=TOP):
    q = select(Prospect)
    q = q.where(Prospect.website.ilike(f"%{domain}%") if domain
                else Prospect.store_name.ilike(f"%{name}%"))
    p = db.execute(q).scalars().first()
    if not p:
        print(f"no prospect matching {domain or name!r}")
        return

    pattern = assess.load_pattern()
    store = assess._scrape(p.website)
    payload = store_payload(store.get("domain") or "", store,
                            store.get("about_text"), assess.tag_signature(pattern))
    depth = (pattern.get("products_per_brand_p10_median_p90") or {}).get("p90")
    gate = unreadable_reason(payload,
                             min_products_per_brand=depth * 2 if depth else None)
    counts = shelf(store)

    print(f"{p.store_name}  ({p.website})")
    print(f"  {p.verdict or 'not assessed'} | {payload['catalogue_size']} products"
          f" | {payload['brand_count']} brands"
          f" | {payload['products_per_brand']} per brand")
    if payload.get("knit_in_band_share") is not None:
        print(f"  {payload['knit_in_band_share']:.0%} of its knitwear priced in our band")
    print(f"  gate: {'GATED — ' + gate if gate else 'not gated'}")
    print("\n  brands, deepest-stocked first:")
    for brand, n in counts.most_common(top):
        print(f"    {n:>5}  {brand}")
    if len(counts) > top:
        print(f"    ... and {len(counts) - top} more")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", nargs="*", help="store name, partial match")
    ap.add_argument("--domain", help="match on website instead")
    ap.add_argument("--top", type=int, default=TOP)
    args = ap.parse_args()

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        report(db, name=" ".join(args.name), domain=args.domain, top=args.top)


if __name__ == "__main__":
    main()
