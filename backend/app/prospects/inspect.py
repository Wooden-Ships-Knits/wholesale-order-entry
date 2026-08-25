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
from types import SimpleNamespace

from sqlalchemy import select

from app.db.models import Prospect

from . import assess
from .analysis.llm_payload import store_payload, unreadable_reason
from .scrapebot.extract import names_knitwear, parse_price, product_blob

TOP = 25
GOODS = 40


def shelf(store):
    """Vendor strings on this shop's shelf, deepest-stocked first."""
    return Counter((p.get("vendor") or "").strip().upper()
                   for p in store["products"] if (p.get("vendor") or "").strip())


def _as_product(p):
    """A cached product dict in the shape the extract rules read.

    They take attributes; the cache holds dicts. Converting here rather than
    re-implementing the rules is the point -- `names_knitwear` warns that a
    second copy of itself would drift silently, and a knit mark that disagreed
    with `knitwear_share` would make this tool worse than no tool.
    """
    return SimpleNamespace(title=p.get("title"), product_type=p.get("product_type"),
                           tags=p.get("tags"), description=p.get("description"))


def goods(store, brand=None):
    """The products themselves, dearest first, optionally one brand only.

    `shelf` answers whose brands are stocked, which is what the house-brand
    gate turns on. It cannot answer what the shop actually SELLS, and that is
    the question asked of a verdict that looks wrong: Phoebe Jon reads as a
    10-brand boutique until you see 114 of its 124 products carry its own name
    and the other nine brands are gloves, belts and scarves.

    Ordered by price because the doubt is nearly always "does this shop sell
    where we sell", which a priced list answers at a glance. An unpriced item
    is unknown rather than free, so it sorts last instead of first.
    """
    want = (brand or "").strip().upper()
    out = []
    for p in store["products"]:
        vendor = (p.get("vendor") or "").strip().upper()
        if want and vendor != want:
            continue
        out.append({
            "title": (p.get("title") or "").strip(),
            "vendor": vendor,
            "price": parse_price(p.get("price")),
            "knit": names_knitwear(product_blob(_as_product(p)), p.get("title") or ""),
        })
    out.sort(key=lambda g: (g["price"] is None, -(g["price"] or 0)))
    return out


def report(db, name=None, domain=None, top=TOP, products=False, brand=None,
           goods_n=GOODS):
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
    # NOT `brand`: a Python loop variable outlives its loop, and this function
    # takes a `brand` argument. Naming them alike silently rebound the caller's
    # brand to the last one printed, so `--brand "PHOEBE JON"` listed J SOCIETY.
    for label, n in counts.most_common(top):
        print(f"    {n:>5}  {label}")
    if len(counts) > top:
        print(f"    ... and {len(counts) - top} more")

    if products or brand:
        items = goods(store, brand=brand)
        who = f" by {brand.upper()}" if brand else ""
        print(f"\n  goods{who}, dearest first "
              f"({len(items)} items; ~ marks what the knitwear rules count):")
        for g in items[:goods_n]:
            shown = f"${g['price']:,.0f}" if g["price"] else "-"
            mark = "~" if g["knit"] else " "
            tail = "" if brand else f"   [{g['vendor'] or 'no brand'}]"
            print(f"    {mark} {shown:>9}  {g['title'][:50]}{tail}")
        if len(items) > goods_n:
            print(f"    ... and {len(items) - goods_n} more")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", nargs="*", help="store name, partial match")
    ap.add_argument("--domain", help="match on website instead")
    ap.add_argument("--top", type=int, default=TOP)
    ap.add_argument("--products", action="store_true",
                    help="also list the goods themselves, dearest first")
    ap.add_argument("--brand", help="list only this brand's goods (implies --products)")
    ap.add_argument("--goods", type=int, default=GOODS, dest="goods_n",
                    help=f"how many goods to print (default {GOODS})")
    args = ap.parse_args()

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        report(db, name=" ".join(args.name), domain=args.domain, top=args.top,
               products=args.products, brand=args.brand, goods_n=args.goods_n)


if __name__ == "__main__":
    main()
