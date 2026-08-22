"""Turn scraped stores into compact payloads an LLM can judge.

Two outputs, because they are sent at different times:

  pattern.json   — what your accounts look like, built once, sent as context
  candidates.jsonl — one line per candidate store, sent one at a time

A catalogue of 2,000 products becomes roughly 500 tokens. Sending the raw
products instead would be ~150x larger, cost accordingly, and bury the few
facts that decide the answer.

  PYTHONPATH=src python analysis/llm_payload.py \
      data/accounts.csv data/raw out/ [data/prospects.csv data/raw-prospects]
"""
import csv
import json
import pathlib
import statistics as st
import sys
from collections import Counter

from ..scrapebot import extract
from .signature import (
    MAX_HOUSE_BRANDS, MIN_CATALOGUE, MIN_HOUSE_CATALOGUE,
    bands, build_tag_signature, load, lift, price_range, profile, store_type,
    tags_of, vendors,
)

TOP_BRANDS = 20          # enough to characterise a shelf, short enough to read
TOP_CATEGORIES = 8
ABOUT_CHARS = 800        # the store's own words, trimmed to the part that says who they are
EXAMPLES = 4             # concrete accounts, so the pattern is not only statistics
SIGNATURE_SHARE = 0.15

# What our own sweaters retail for on a shop floor, stated by the business
# rather than measured from a catalogue. It replaces the account band for
# knitwear price because rule 3 asks whether a store can shelve OUR product,
# and the measured band answered a neighbouring question — where our existing
# accounts happen to sit. The two diverge: 57% of accounts price their own
# knitwear below $100, against a median of $95.
OUR_KNIT_RETAIL = (100.0, 150.0, 200.0)


def _category_mix(store, limit=TOP_CATEGORIES):
    types = Counter((p.get("product_type") or "").strip().upper()
                    for p in store["products"] if (p.get("product_type") or "").strip())
    total = sum(types.values())
    if not total:
        return {}
    return {t: round(n / total, 3) for t, n in types.most_common(limit)}


def _prices(store):
    vals = sorted(p["price"] for p in store["products"] if p.get("price"))
    if not vals:
        return None
    at = lambda q: round(vals[int(q * (len(vals) - 1))])  # noqa: E731
    return [at(0.25), at(0.50), at(0.75)]


def _knit_tags(tags):
    """The store's own tags that name knitwear, judged by the scraper's rule.

    Kept apart from signature_tags_carried, which answers a different question:
    that one asks whether a shop is merchandised like our customers, and only
    three of its 78 tags name knitwear at all. This is the shop saying, in its
    own words, that it sells the thing we make.
    """
    return sorted(t for t in tags if extract.names_knitwear(t))


def _knit_evidence(knit_share, knit_tags):
    """Where the knitwear evidence came from, or that there is none.

    The filter hangs off this, so it names its sources rather than reducing to
    a boolean: a shop whose knitwear is visible only in its product titles is a
    real prospect, and measured across 271 accounts that is 93 of them against
    zero the other way round. A tag-only gate would discard every one.

    "products" is knit_share, read rather than recomputed, so the label and the
    number it describes cannot disagree. It already covers title, product_type,
    tags and description together. The tag half is called out separately
    because it is the store's own vocabulary, and it is the half that goes
    missing for a shop that tags nothing but promotions.
    """
    products_say = bool(knit_share)
    if knit_tags and products_say:
        return "tags+products"
    if products_say:
        return "products_only"
    if knit_tags:
        return "tags_only"
    return "none"


def store_payload(domain, store, about, tag_signature=frozenset()):
    """One store, compact enough to send but complete enough to judge.

    Three questions, in the order a buyer would ask them: does this shop buy
    from brands at all, does it sell our kind of thing, and can it afford us.
    """
    pr = profile(store)
    brands = vendors(store)
    tags = tags_of(store)
    knit_tags = _knit_tags(tags)
    return {
        "domain": domain,
        "catalogue_size": pr["catalogue"],
        "brand_count": len(brands),
        # How deeply the store backs each brand, and what that makes it. A shop
        # carrying 26 brands stocks ~11 products of each; a label carrying two
        # stocks 267 of each and buys from nobody.
        "products_per_brand": (round(pr["catalogue"] / len(brands), 1)
                               if brands else None),
        "store_type": store_type(store),
        "top_brands": [b for b, _ in Counter(
            (p.get("vendor") or "").strip().upper()
            for p in store["products"] if (p.get("vendor") or "").strip()
        ).most_common(TOP_BRANDS)],
        "category_mix": _category_mix(store),
        "signature_tags_carried": sorted(tag_signature & tags),
        "tag_lift": lift(tags, tag_signature) if tag_signature else None,
        "price_p25_p50_p75": _prices(store),
        "price_range": price_range(store),
        "knitwear_share": round(pr["knit_share"], 3),
        "knitwear_price_median": pr["knit_price_median"],
        "knit_tags_carried": knit_tags,
        "knit_evidence": _knit_evidence(pr["knit_share"], knit_tags),
        "about_text": (about or "")[:ABOUT_CHARS],
    }


def _labelled(band, places=None):
    """A band with its edges named.

    A bare [194.01, 490.0, 1494.6] reads as a two-ended range with a stray
    number in the middle. A model did exactly that — took the median for the
    upper bound and called a store outside a band it was comfortably inside.
    """
    if band is None:
        return None
    values = [round(v, places) if places is not None else v for v in band]
    return dict(zip(("p10", "median", "p90"), values))


def _rules(depth_band):
    """How each measurement below becomes a decision.

    Carried inside the pattern rather than left in prompt.md alone, because a
    number without its rule invites the reader to invent one. Two real cases:
    a three-value band read as a two-ended range, and price_range cited as
    though it were the knitwear band. Both numbers were present and correct;
    what was missing was what to do with them.

    Thresholds are read from the constants that enforce them, so the
    explanation cannot drift away from the behaviour.
    """
    median = depth_band["median"] if depth_band else None
    return {
        "what_this_is": (
            "The profile of stores that already buy from us, and the rules we "
            "judge a candidate against. Everything here is measured from product "
            "catalogues, never from revenue: a candidate has no purchase history "
            "with us, so a rule built on it could not be applied to both sides. "
            "One figure is not measured and says so where it appears: "
            "bands_p10_median_p90.knit_price_median is our own retail price."
        ),
        "bands": (
            "Every band is {p10, median, p90}. The range our accounts occupy runs "
            "from p10 to p90; the median is the middle of that range, never an "
            "edge. Read a band as where our accounts sit, not as a target — a "
            "candidate outside one is different, not disqualified, and you say how. "
            "knit_price_median is the exception and reads the other way round: it "
            f"is what our own sweaters retail for (${OUR_KNIT_RETAIL[0]:.0f}–"
            f"${OUR_KNIT_RETAIL[2]:.0f}), so it IS a target. A shop whose knitwear "
            "sits far below it cannot carry our price."
        ),
        "signature_tags": (
            "A fingerprint of how our accounts describe their own stock, measured "
            "from their shelves — not a list of what we want a store to sell. "
            "Jewelry leads it because 47% of our accounts sell jewelry, and only "
            "three of these tags name knitwear at all. Read a match as evidence "
            "that a shop is merchandised like our customers are; whether it sells "
            "sweaters is knitwear_share and knit_tags_carried, measured "
            "separately. A candidate with none of these tags is not thereby a "
            "poor fit: it may simply tag its stock in another vocabulary, or in "
            "promotions only, and that is a fact about its website rather than "
            "its shelf."
        ),
        "order": (
            "Answer the rules in order. The first discards shops that cannot "
            "become customers at all, so the other two need not be weighed until "
            "it passes."
        ),
        "rules": [
            {
                "question": "Does this shop buy from brands at all?",
                "reads": ["store_type", "brand_count", "products_per_brand"],
                "against": "store_type_mix, products_per_brand_p10_median_p90",
                "why": (
                    "A shop selling only its own label has no buyer and no budget "
                    "for outside brands. It cannot become a wholesale account "
                    "however well the rest fits — this is a harder fact than any "
                    "similarity score."
                ),
                "disqualifies": {"max_brands": MAX_HOUSE_BRANDS,
                                 "min_catalogue": MIN_HOUSE_CATALOGUE,
                                 "verdict": "weak"},
                "unreadable_below_catalogue": MIN_CATALOGUE,
                "evidence": (
                    f"A boutique stocks about {median} products per brand; a label "
                    "stocks hundreds. Two conditions decide it, not one, so a thin "
                    "catalogue from a failed scrape is not mistaken for a label."
                ),
            },
            {
                "question": "Does it sell our kind of thing?",
                "reads": ["knit_evidence", "knit_tags_carried", "knitwear_share",
                          "signature_tags_carried", "tag_lift", "category_mix"],
                "against": "signature_tags, bands_p10_median_p90.knit_share",
                "why": (
                    "A shop already selling sweaters is the opening: it has a "
                    "knitwear buyer and shelf space to put us on."
                ),
                "disqualifies": {"knit_evidence": "none", "verdict": "weak"},
                "evidence": (
                    "knit_evidence names where the knitwear was found: in the "
                    "shop's own tags, in its products, in both, or nowhere. "
                    "'products_only' is not a weaker answer than 'tags+products' "
                    "-- of 271 accounts, 97 show knitwear in their products "
                    "alone and none in tags alone, so a shop that never writes "
                    "the word in a tag is the ordinary case, not a doubtful one."
                ),
                "caution": (
                    "A low tag_lift is weak evidence, not proof of a poor fit. "
                    "18% of our own accounts would score zero, because they "
                    "describe their stock in their own words. An empty "
                    "signature_tags_carried says the shop does not share our "
                    "accounts' vocabulary -- often because it tags nothing but "
                    "promotions -- and is never an argument against it on its "
                    "own. Read knit_tags_carried and knitwear_share instead."
                ),
            },
            {
                "question": "Can it afford us, and can we afford it?",
                "reads": ["price_p25_p50_p75", "price_range",
                          "knitwear_price_median"],
                "against": ("bands_p10_median_p90.price_median, .price_range, "
                            ".knit_price_median"),
                "why": (
                    "Price is the sharpest disqualifier. Our sweaters retail at "
                    f"${OUR_KNIT_RETAIL[0]:.0f}–${OUR_KNIT_RETAIL[2]:.0f}, so read "
                    "knitwear_price_median against that directly: a shop whose "
                    "knitwear sits far below cannot carry our price, however well "
                    "the rest fits. price_median and price_range stay account "
                    "bands — where our customers sit, not targets."
                ),
                "caution": (
                    "Name the band you cite. price_median is a shop's middle "
                    "price, price_range the spread between its cheapest and "
                    "dearest item, knit_price_median the middle price of its "
                    "knitwear only. Comparing against the wrong one produces a "
                    "sentence that reads correctly and is false."
                ),
            },
        ],
    }


def build_pattern(accounts, about, tag_signature, counts):
    """The profile of stores that already buy from us, as one sendable object.

    Built here rather than inline in main() so the shape can be tested without
    a scrape behind it.
    """
    profiles = [{**profile(s), "price_range": price_range(s)}
                for s in accounts.values()]
    types = Counter(store_type(s) for s in accounts.values())

    # Measured on the boutiques only. One own-label store carries hundreds of
    # products under a single name, which would drag the band away from every
    # shop the band is meant to describe.
    depths = [{"ppb": len(s["products"]) / len(vendors(s))}
              for s in accounts.values()
              if vendors(s) and store_type(s) == "multi_brand"]

    # Statistics say what the middle looks like; examples say what a real one
    # looks like. An LLM given only bands tends to reason about the bands.
    ranked = sorted(accounts.items(),
                    key=lambda kv: -lift(tags_of(kv[1]), tag_signature))
    examples = [store_payload(d, s, about.get(d), tag_signature)
                for d, s in ranked[:EXAMPLES]]

    depth_band = _labelled(bands(depths, "ppb") if depths else None, places=1)

    return {
        "how_to_read_this": _rules(depth_band),
        "store_count": len(accounts),
        "store_type_mix": {k: round(v / len(accounts), 3)
                           for k, v in types.most_common()},
        "products_per_brand_p10_median_p90": depth_band,
        "signature_tags": [
            {"tag": t, "share_of_accounts": round(counts[t] / len(accounts), 3)}
            # Ties broken by name: the signature is a set, so equal counts would
            # otherwise come out in hash order and every rebuild would diff.
            for t in sorted(tag_signature, key=lambda t: (-counts[t], t))
        ],
        "bands_p10_median_p90": {
            **{k: _labelled(bands(profiles, k)) for k in
               ("knit_share", "price_median", "price_range")},
            # Stated, not measured. Named as such in how_to_read_this, because a
            # band that looks like the others and is not would go uncaught.
            "knit_price_median": _labelled(OUR_KNIT_RETAIL),
        },
        "example_accounts": examples,
    }


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def skip_reason(payload):
    """Why this store is not worth a model call, or None if it is.

    Judging costs one call per store, and a shop with no knitwear anywhere has
    already answered rule 2 against itself -- `check()` would force the same
    `weak` the model was paid to reach. Measured on one run: 5 of 28 candidates.

    An unreadable shop is deliberately not skipped. It has no knitwear either,
    but that is our failure rather than a fact about the shop, and it reads as
    `insufficient_data` -- filing it under "no knitwear" would state something
    about a shelf nobody managed to see.
    """
    if payload.get("store_type") == "insufficient_data" or not payload.get("catalogue_size"):
        return None
    if payload.get("knit_evidence") == "none":
        return "nothing in the catalogue names knitwear"
    return None


def read_about(input_csv):
    """domain -> about_text, from whichever output directory holds that run.

    Runs land in data/out, data/out-fl, data/out-top10 and so on, so the table
    is looked up rather than assumed. A missing table costs the About text and
    nothing else, so it warns instead of stopping.
    """
    stem = pathlib.Path(input_csv).stem
    found = sorted(pathlib.Path("data").glob(f"out*/{stem}-companies.csv"))
    if not found:
        print(f"  note: no companies table for {stem} — payloads will omit About text")
        return {}

    csv.field_size_limit(10 ** 9)
    out = {}
    with open(found[0], newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("domain") and row.get("about_text"):
                out[row["domain"]] = row["about_text"]
    return out


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    accounts_csv, accounts_raw, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    accounts = load(accounts_csv, accounts_raw)
    about = read_about(accounts_csv)

    signature, counts = build_tag_signature(list(accounts.values()), SIGNATURE_SHARE)
    pattern = build_pattern(accounts, about, signature, counts)

    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "pattern.json").write_text(json.dumps(pattern, indent=1), encoding="utf-8")
    print(f"pattern.json      {len(signature)} tags, {len(accounts)} accounts, "
          f"{len(json.dumps(pattern)) // 4:,} tokens (approx)")

    if len(sys.argv) > 5:
        cands = load(sys.argv[4], sys.argv[5], exclude=set(accounts))
        cand_about = read_about(sys.argv[4])
        path, skipped_path = out / "candidates.jsonl", out / "skipped.jsonl"
        sizes, skipped = [], []
        with open(path, "w", encoding="utf-8") as fh:
            for d, s in cands.items():
                payload = store_payload(d, s, cand_about.get(d), signature)
                reason = skip_reason(payload)
                if reason:
                    skipped.append({"domain": d, "reason": reason,
                                    "catalogue_size": payload["catalogue_size"]})
                    continue
                line = json.dumps(payload, ensure_ascii=False)
                sizes.append(len(line) // 4)
                fh.write(line + "\n")
        # Written even when empty, so a run never leaves last run's list behind
        # to be read as this one's.
        _write_jsonl(skipped_path, skipped)

        median = f"~{int(st.median(sizes)):,} tokens each, " if sizes else ""
        print(f"candidates.jsonl  {len(sizes)} stores, {median}{sum(sizes):,} total")
        # Named rather than counted. A silent prefilter reads from outside like
        # a list that was always this short, and these are stores a rep might
        # otherwise go looking for.
        print(f"skipped.jsonl     {len(skipped)} stores, unjudged")
        for row in skipped:
            print(f"   {row['domain']}: {row['reason']}")


if __name__ == "__main__":
    main()
