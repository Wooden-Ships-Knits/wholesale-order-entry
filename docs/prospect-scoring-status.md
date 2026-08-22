# Prospect scoring — status, 2026-08-22

The scrapebot integration, and the first end-to-end run of it. Nothing below is
committed yet; branch `feat/dev-environment`.

## The run

All 92 prospects with a website were scraped, scored and judged against the dev
database. 92 written, 0 failures, 0 left pending. Two passes: the first built
the page cache, the second re-judged everything after `pattern.json` was
replaced (see "Pattern" below).

| verdict | count | flagged `problems` |
|---|---|---|
| insufficient_data | 54 | 7 |
| weak | 35 | 0 |
| possible | 3 | 0 |
| strong | 0 | — |

The three `possible` shops, all `multi_brand` with knitwear in both tags and
products: **Coast By Driftwood** (HI, 176 brands, $90 median), **Loveworn** (CA,
42 brands, $32), **LSpace** (CA, 14 brands, $114). All three came back
`confidence: medium`, so all three want a human eye before a rep spends a call.

### 33% of the run was lost to the scraper, not to the shops

This is the headline finding and it is invisible unless the two failure modes
are told apart:

| why `insufficient_data` | count |
|---|---|
| scraper got an `error` | 14 |
| site read fine, catalogue empty | 14 |
| `js_required` — SPA storefront | 12 |
| model judged the catalogue too small | 10 |
| scraper `blocked` | 4 |

**30 of 92 (33%) failed on fetching, not on merit.** Those shops are recorded as
"not enough data" when what was missing was the scraper's reach. A third of the
scrape budget bought nothing, and a third of Rande's shortlist has not actually
been assessed. `js_required` is the tractable one — twelve Shopify/Squarespace
storefronts that render their catalogue client-side.

Cost is not the constraint: ~18s per shop (1.5s/host throttle x up to 25 pages)
against roughly $0.10 of `gpt-4o-mini`. Scrape reach is.

## What is here

| path | what |
|---|---|
| `backend/app/prospects/` | the scrapebot, vendored — see its README.md |
| `backend/app/prospects/assess.py` | scrape → score → judge → write the row |
| `backend/app/maps/prospect_store.py` | sweep output → `prospects` (upsert) |
| `backend/app/db/migrations/.../0023_prospect_assessment.py` | applied to dev |
| `docker-compose.tools.yml` | Adminer overlay, `127.0.0.1:8081` |
| `backend/tests/test_prospect_assess.py` | 13 tests |
| `backend/tests/test_prospect_store.py` | 14 tests |
| `prospects_stale_pattern_snapshot` (dev db) | verdicts from before the pattern
swap, kept for comparison. Safe to drop. |

## Fixed in this pass

**The data was never all California.** 29 of the 225 rows are Hawaii — Honolulu,
Hilo, Lahaina, Kailua-Kona. The territory is `CA/HI - Rande Cohen` and
`states_for_territory` returns `['CA', 'HI']`; an earlier version of this file
said "the data is California", and backfilling on that would have mislabelled 29
shops in the column that exists to filter a territory that straddles a border.
Backfilled from longitude instead: 1,300 miles of open Pacific separates the two
groups and no row sits in between. One of the three `possible` shops is Hawaiian.

**`state` was dropped silently, at both ends.** `discover_osm` never wrote it
(it queries one state at a time and knew it all along) and `prospect_store.FIELDS`
never mapped it. Both fixed, so the next sweep carries it without a backfill.

**`territory` was NULL on all 225 rows**, and `/reps/prospects` filters on it,
so every one of them was invisible to every rep. Set to `CA/HI - Rande Cohen`,
which is spelled identically in Salesforce and in the REGION sheet — checked,
because the filter matches Salesforce's spelling and the sheet's independently.

**`_prospect_row` swallowed the whole assessment.** It now passes `verdict`,
`confidence`, `for_the_rep`, `reasons`, `against`, `problems` and `assessed_at`,
always present and null rather than absent, so the page can tell "nobody has
looked yet" from "looked, and weak". `ProspectTable` grew an **Assessment**
column. Key set pinned by `test_prospect_row_serializes_exactly_the_allowed_keys`.

**"site could not be read: ok"** — `assess.py` collapsed two different findings
into one message, and `reasons` is the only place either is explained to a rep.
Split into "could not be read: {status}" and "was read but lists no products".
The whole failure table above is only legible because of this.

**`prospect_store.py` was invisible to git** (`.gitignore:32` is `maps/`, which
protects nothing and hid source). Force-added; consider deleting the line.

**The image was rebuilt from source.** It previously held a `docker cp` of
`prospect_store.py`.

## Pattern

`pattern.json` was stale — its rule 2 never mentioned `knit_evidence`, so the
model was not told the rule `judge.check()` holds it to. **No rebuild was
needed:** `scrapping-bot/data/llm-rande/pattern.json` (built 2026-08-21) already
carries the gate. Copied over; provenance recorded in the prospects README.

The 78 `signature_tags` are byte-identical between the two, so the swap changes
what the model is TOLD, never what is MEASURED. Re-judging all 92 from the cache
moved 2 verdicts, both `possible` → `weak`.

**That delta is not clean evidence of the swap, and an earlier version of this
file claimed it was.** The model is not deterministic at `temperature=0`:
lspace.com, scored five times over the same cached catalogue and the same
pattern, came back `possible` four times and `weak` once — and lspace.com is one
of the three shops the swap supposedly moved. A 2-of-92 delta is inside the
noise. To measure a prompt change, score the same shop N times before and after
and compare the spread; `notebooks/assess-one-website.ipynb` §6 does this.

## Open

1. **`judge.py:133` flags 7 honest answers.** `skip_reason`
   (`llm_payload.py:338`) deliberately does NOT gate a shop whose catalogue is
   empty or unreadable — "filing it under 'no knitwear' would state something
   about a shelf nobody managed to see" — so it goes to the model, which
   correctly answers `insufficient_data`. `check()` then flags every non-`weak`
   verdict with `knit_evidence == "none"`, with no matching carve-out, so all 7
   read as "do not trust this row" when they are right. The pattern swap cannot
   fix this; it is code. **`judge.py` is byte-identical to upstream, so fixing
   it here creates drift** — fix it in `scrapping-bot` and re-vendor, or patch
   here and record the drift in the README.
2. **Scrape reach**, per the 33% above. `js_required` (12 shops) is the
   tractable slice.
3. OSM duplicates: "Barefoot Boutique" is two elements sharing one website. Both
   were scraped, but the cache made the second free — the real cost is one extra
   model call, which is not worth dedup code.
4. 133 of the 225 rows have no website and can never be assessed by this path.
5. **Verdicts near a rule boundary are unstable run to run** (see Pattern above).
   `_openai_complete` sets `temperature=0` with the comment "the same shop must
   not get two answers"; that is not what temperature 0 buys, and the comment has
   been corrected. Nothing currently records how confident a verdict is in this
   sense — a shop that scores 5/5 `weak` and one that scores 3/5 `weak` are
   written to the row identically. Scoring N times and storing the spread, or
   taking a majority, would fix it and would cost N model calls per shop.
