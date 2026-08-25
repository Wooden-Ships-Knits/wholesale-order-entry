"""Calibrate the tag signature against a background set, and report what it found.

This script measures; it does not rank. Ranking candidates is `llm_payload.py`,
which builds what the model actually reads. Keeping the two apart means the
threshold can be re-measured without touching the payload, and the payload can
change without silently invalidating the threshold behind it.

Reads only the raw JSON the scraper already wrote. Makes no network requests.

  PYTHONPATH=src python analysis/signature.py \
      data/accounts.csv data/raw [data/background.csv data/raw-background]

The second pair is a background set: comparable shops that are NOT customers.
Without it the threshold reported is a default, not a measurement.
"""
import hashlib
import json
import pathlib
import re
import statistics as st
import sys
from collections import Counter

from ..scrapebot import extract
from ..scrapebot.models import Product
from ..scrapebot.resolve import canonical_domain, read_rows, website_of

# Your own brand, excluded from the signature: a prospect never carries it, so
# including it would score every prospect down for the one thing they can't have.
OWN_BRAND = "wooden ships"

SHARE_CANDIDATES = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40)
MIN_BRAND_COUNT = 3          # a brand on fewer shelves than this is a coincidence
MIN_SIGNATURE_SIZE = 5       # below this the signature is too thin to rank with
HOLDOUT_BUCKETS = 2


def _own(brand):
    return OWN_BRAND in (brand or "").lower()


def vendors(store):
    """Distinct brand names on this store's shelf, upper-cased."""
    return {(p.get("vendor") or "").strip().upper()
            for p in store["products"] if (p.get("vendor") or "").strip()}


def brand_depths(store):
    """How many products each brand on this shelf carries, deepest first.

    `vendors` answers WHICH brands are stocked; this answers how deeply each
    one is backed, which is the difference between a boutique and a label
    wearing a boutique's brand count.
    """
    return Counter((p.get("vendor") or "").strip().upper()
                   for p in store["products"] if (p.get("vendor") or "").strip())


def top_brand_share(store):
    """What share of the catalogue its single deepest-stocked brand holds.

    THE MEAN CANNOT SEE A HOUSE BRAND HIDING BEHIND ACCESSORIES. Phoebe Jon
    carries 114 of its own 124 products, and nine further "brands" holding one
    glove, one belt and one scarf apiece. That is 92% concentration -- but a
    mean of 12.4 products per brand, which is an ordinary boutique's number,
    so `products_per_brand` waved it through as `strong` at high confidence.
    Nine one-product labels are enough to dilute any mean; they cannot dilute
    a share.

    This is the same error already fixed once on price, where a median hid the
    distribution. A mean hides concentration.

    None when no product names a brand at all -- a different fact from "one
    brand holds everything", and one the caller must not read as 100%.
    """
    depths = brand_depths(store)
    total = sum(depths.values())
    if not total:
        return None
    return depths.most_common(1)[0][1] / total


def tags_of(store):
    """Distinct tags on this store's shelf, upper-cased.

    The store's own vocabulary for what it sells. Noisier than brands — 88% of
    tags appear on a single shelf, against 73% of brands — so it is only usable
    after the same recurrence test.
    """
    return {t.strip().upper() for p in store["products"]
            for t in (p.get("tags") or []) if t and t.strip()}


def price_range(store):
    """The spread between cheapest and dearest, or None with no prices.

    Read beside the median, not instead of it: two shops can share a median and
    still be different shops, one spanning $2-$545 and the other $39-$698.
    """
    prices = sorted(p["price"] for p in store["products"] if p.get("price"))
    return (prices[-1] - prices[0]) if prices else None


def carries_own_brand(store):
    titles = " ".join(p["title"] for p in store["products"])
    return _own(titles) or any(_own(v) for v in vendors(store))


# A shelf this narrow, backed by a catalogue this full, is one label rather than
# a shop: the store makes what it sells and buys from nobody.
_ALNUM_RE = re.compile(r"[^a-z0-9]")

MAX_HOUSE_BRANDS = 3
MIN_HOUSE_CATALOGUE = 200
MIN_CATALOGUE = 50           # below this we have not read enough to judge at all


def brands_echo_domain(domain, top_brands, n=3):
    """Whether this shop's leading "brands" are just its own name.

    Deep catalogues arrive in two shapes that a catalogue cannot tell apart: a
    label that makes everything it sells, and a boutique whose site never fills
    the vendor field so every product carries the shop's name. Both read as one
    brand stocked hundreds deep.

    We do not know which one we are looking at, so the caller must answer
    `insufficient_data` -- never `weak`. Nine of our own 242 accounts classify
    as house_brand, and burlapranch.com lists all 2,000 of its products under
    "BURLAP RANCH MERCANTILE". Calling that shape a bad prospect would libel
    paying customers.

    Compared on letters and digits only, both directions, because a vendor
    string is typed by hand: "HILL HOUSE HOME" against hillhousehome.com is the
    same shop, and "RAILS" against latreclothingca.com is not.
    """
    label = _ALNUM_RE.sub("", (domain or "").split(".")[0].lower())
    if not label:
        return False
    for brand in list(top_brands or [])[:n]:
        b = _ALNUM_RE.sub("", (brand or "").lower())
        if b and (b in label or label in b):
            return True
    return False


def store_type(store):
    """Whether this store buys from outside brands at all.

    A store selling only its own label has no buyer and no budget for other
    brands, so it cannot become a wholesale account however well the rest fits.
    That is a harder fact than any similarity score, which is why it is decided
    here rather than left to the ranking.

    Told apart from a thin scrape by catalogue size. 640 products under one
    brand is a label; 4 products under one brand is our own failure to read the
    site. Judging those the same would punish a store for our error.
    """
    products = store["products"]
    brands = vendors(store)
    if len(products) < MIN_CATALOGUE or not brands:
        return "insufficient_data"
    if len(brands) <= MAX_HOUSE_BRANDS and len(products) >= MIN_HOUSE_CATALOGUE:
        return "house_brand"
    return "multi_brand"


def load(csv_path, raw_dir, exclude=frozenset()):
    """Domain -> raw store record, for domains with usable brand data.

    A store with no vendor field cannot be scored, so it is left out rather
    than counted as a store carrying nothing.
    """
    wanted = {canonical_domain(website_of(r)) for r in read_rows(csv_path)} - {""} - set(exclude)
    out = {}
    for f in pathlib.Path(raw_dir).iterdir():
        if f.stem not in wanted:
            continue
        try:
            store = json.loads(f.read_text())
        except (ValueError, OSError):
            continue                       # a file the scraper is mid-write on
        if store["products"] and vendors(store):
            out[f.stem] = store
    return out


def _recurring(stores, share, terms_of, skip=lambda _: False):
    """Terms appearing on at least `share` of these shelves, and their counts.

    Shared by both signatures so they cannot drift apart: a tag on two shelves
    is a coincidence for exactly the reason a brand on two shelves is.
    """
    counts = Counter()
    for store in stores:
        for term in terms_of(store):
            if not skip(term):
                counts[term] += 1
    floor = max(MIN_BRAND_COUNT, len(stores) * share)
    return {t for t, c in counts.items() if c >= floor}, counts


def build_signature(stores, share):
    """Brands recurring across at least `share` of these stores' shelves."""
    return _recurring(stores, share, vendors, skip=_own)


def build_tag_signature(stores, share):
    """The store's own words for what it sells, kept where they recur.

    Where brands say whose shelf you would share, tags say what kind of shop it
    is. Weaker at telling accounts from strangers, but it reaches further: 18%
    of accounts score zero on tags against 28% on brands.
    """
    return _recurring(stores, share, tags_of)


def lift(brands, signature):
    """Signature hits, normalised for how broad the catalogue is.

    A store carrying 400 brands hits more of any list than one carrying 40, so
    the raw count rewards breadth rather than fit. One real case: a prospect
    with 165 brands scored 13 hits, out-ranking accounts that fit far better.
    """
    if not signature:
        return 0.0
    expected = max(1.0, len(brands) * (len(signature) / 1000))
    return round(len(signature & brands) / expected, 2)


def _percentiles(vals):
    """p25/p50/p75, index-truncated and rounded.

    The same method as llm_payload._prices, deliberately: a candidate figure and
    the account band it is read against have to be computed the same way, or the
    comparison is between two different statistics wearing one name.
    """
    if not vals:
        return None
    at = lambda q: round(vals[int(q * (len(vals) - 1))])  # noqa: E731
    return [at(0.25), at(0.50), at(0.75)]


def profile(store, band=None):
    """What this store sells, in the terms a catalogue can answer.

    Deliberately excludes revenue: a candidate has none, so any dimension built
    on it cannot be compared across the two sides.

    `band` is (low, ..., high) — what OUR knitwear retails for. Given, the
    profile also reports what share of the shop's knitwear falls inside it,
    which is the question rule 3 actually wants answered.
    """
    products = [Product(title=p["title"], price=p.get("price"),
                        vendor=p.get("vendor") or "",
                        product_type=p.get("product_type") or "",
                        tags=p.get("tags") or [],
                        description=p.get("description") or "")
                for p in store["products"]]
    knits = extract.knit_products(products)
    prices = sorted(p.price for p in products if p.price)
    knit_prices = sorted(p.price for p in knits if p.price)
    return {
        "catalogue": len(products),
        "knit_share": len(knits) / len(products) if products else 0.0,
        "price_median": st.median(prices) if prices else None,
        "knit_price_median": st.median(knit_prices) if knit_prices else None,
        # The median alone decided rule 3, and a median is not a floor. A shop
        # at $218 was rejected while a third of its knitwear sat inside our
        # band; a shop $32 dearer had none there at all. One number cannot tell
        # those apart, so the spread is carried too.
        "knit_price_p25_p50_p75": _percentiles(knit_prices),
        "knit_in_band_share": (
            round(sum(1 for x in knit_prices if band[0] <= x <= band[-1])
                  / len(knit_prices), 3)
            if knit_prices and band else None),
    }


def bands(profiles, key, low=0.10, high=0.90):
    """The p10-median-p90 band of one dimension across the accounts.

    A band rather than an average: stores that buy from you are not clustered
    on a point, and an average would invent a typical store that does not exist.
    """
    vals = sorted(p[key] for p in profiles if p[key] is not None)
    if not vals:
        return None
    at = lambda q: vals[int(q * (len(vals) - 1))]  # noqa: E731
    return at(low), at(0.50), at(high)


def within(value, band):
    """Whether a candidate sits inside the account band. None means unknown."""
    if value is None or band is None:
        return None
    return band[0] <= value <= band[2]


def split(domains):
    """Stable halves, so the holdout does not shift with filesystem order."""
    def bucket(d):
        return int(hashlib.md5(d.encode()).hexdigest(), 16) % HOLDOUT_BUCKETS
    return ([d for d in domains if bucket(d) == 0],
            [d for d in domains if bucket(d) != 0])


def calibrate(build, test, background):
    """Choose the share threshold that best separates accounts from background.

    Measured on tags, because that is what the payload scores on. Scored on the
    gap between medians, so a threshold that lifts both equally earns nothing.
    With no background supplied this cannot discriminate, and the caller is told
    so rather than handed a confident number.
    """
    best, table = None, []
    for share in SHARE_CANDIDATES:
        sig, _ = build_tag_signature(build, share)
        if len(sig) < MIN_SIGNATURE_SIZE:
            table.append((share, len(sig), None, None, None))
            continue
        held = st.median([lift(tags_of(s), sig) for s in test])
        bg = st.median([lift(tags_of(s), sig) for s in background]) if background else 0.0
        gap = held - bg
        table.append((share, len(sig), held, bg, gap))
        if best is None or gap > best[1]:
            best = (share, gap)
    return (best[0] if best else 0.20), table


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    accounts = load(sys.argv[1], sys.argv[2])
    background = (load(sys.argv[3], sys.argv[4], exclude=set(accounts))
                  if len(sys.argv) > 4 else {})

    listing = sum(1 for s in accounts.values() if carries_own_brand(s))
    print(f"accounts with catalogue data: {len(accounts)}  "
          f"(of which list your brand online: {listing})")
    print(f"background stores:            {len(background)}")
    if not background:
        print("  no background set: the threshold below is a default, not a measurement")

    types = Counter(store_type(s) for s in accounts.values())
    print("  store types: " + ", ".join(f"{k} {v}" for k, v in types.most_common()))

    # Every account is an existing partner, so all of them are valid training
    # data. Restricting to those that merchandise the brand online would drop
    # two thirds of it for a reason unrelated to whether they buy.
    build_doms, test_doms = split(sorted(accounts))
    build = [accounts[d] for d in build_doms]
    test = [accounts[d] for d in test_doms]

    share, table = calibrate(build, test, list(background.values()))
    print(f"\n{'share':>7}{'tags':>8}{'accounts':>10}{'background':>12}{'gap':>8}")
    for s, n, h, b, gap in table:
        if gap is None:
            print(f"{s:>7.0%}{n:>8}      (signature too thin)")
        else:
            print(f"{s:>7.0%}{n:>8}{h:>10.2f}{b:>12.2f}{gap:>8.2f}"
                  f"{'  <-' if s == share else ''}")

    sig, _ = build_tag_signature(build, share)
    held = sorted(lift(tags_of(s), sig) for s in test)
    zero = sum(1 for x in held if x == 0)
    print(f"\nthreshold {share:.0%} -> {len(sig)} tags, from {len(build)} accounts")
    print(f"held-out accounts (n={len(held)}): median tag_lift {st.median(held):.2f}, "
          f"{zero} scoring zero")

    full, full_counts = build_tag_signature(list(accounts.values()), share)
    print(f"\nfull signature ({len(accounts)} accounts): {len(full)} tags")
    for tag, c in sorted(((x, full_counts[x]) for x in full), key=lambda x: -x[1])[:20]:
        print(f"   {c:>4}/{len(accounts)}  {tag[:44]}")

    # What accounts sell, in catalogue terms. No revenue: a candidate has none,
    # so a dimension built on it could never be compared across the two sides.
    profiles = [{**profile(s), "price_range": price_range(s)}
                for s in accounts.values()]
    dims = [("knit_share", "knitwear share", "{:.0%}"),
            ("price_median", "store price", "${:.0f}"),
            ("price_range", "price spread", "${:.0f}"),
            ("knit_price_median", "knitwear price", "${:.0f}")]

    print(f"\naccount profile, from product data only ({len(profiles)} stores)")
    for key, label, fmt in dims:
        b = bands(profiles, key)
        if b:
            print(f"   {label:<18} p10 {fmt.format(b[0]):>8}"
                  f"   median {fmt.format(b[1]):>8}   p90 {fmt.format(b[2]):>8}")


if __name__ == "__main__":
    main()
