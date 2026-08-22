# Prospect scoring — vendored from `scrapping-bot`

Copied from the `scrapping-bot` repository at commit **fc0cee1**, 2026-08-22.

The sweep in `app/maps/prospecting.py` finds shops that EXIST. This answers
whether one is worth a rep's time, by reading the shop's own catalogue.

## What is here

| path | origin | changed? |
|---|---|---|
| `scrapebot/` (7 files) | `src/scrapebot/` | **byte-identical** |
| `analysis/judge.py` | `analysis/judge.py` | **byte-identical** |
| `analysis/prompt.md` | `analysis/prompt.md` | **byte-identical** |
| `analysis/llm_payload.py` | same | 6 lines: imports only |
| `analysis/signature.py` | same | 7 lines: imports only |
| `pattern.json` | `data/llm/pattern.json` | **byte-identical** |
| `assess.py` | — | **new here** |

The only edits to copied code were three `sys.path.insert` hacks removed and
five imports made relative. Nothing else was touched, so `diff` against
upstream still reads cleanly — which is the whole reason to keep the filenames
and the module layout identical.

## What was deliberately NOT copied

**The HTTP API and the SQLite job queue** (`src/scrapebot_api/`: `app.py`,
`worker.py`, `jobs.py`, `osm.py`, `pipeline.py`). They exist to bridge two
separate processes. In here the scoring code is a function call away and
Postgres is already open, so a queue would only add a second place for a job to
get stuck, a second database to back up, and a network hop between two
containers that currently cannot see each other anyway.

`osm.py` went with them: it looked an element up to find its website, and the
sweep has already written that into `prospects.website`.

**The batch/CSV tooling** (`scrapebot/cli.py`, `tables.py`, `aggregate.py`,
`google_sheet.py`, `__main__.py`). Nothing here reaches them — that is the
other repo's job, and it still does it.

## Rebuilding `pattern.json`

Not possible from this repository, on purpose. It is built from 242 account
catalogues that live in `scrapping-bot/data/`, and it is a model artifact, not
configuration:

    cd scrapping-bot
    PYTHONPATH=src python analysis/llm_payload.py \
        data/accounts-l5y.csv data/raw data/llm

then copy `data/llm/pattern.json` over the one here.

**Resolved 2026-08-22.** The copy first vendored here predated the knitwear
gate: its rule 2 never mentioned `knit_evidence`, so the model was not told the
rule `judge.check()` holds it to, and gated shops came back carrying avoidable
`problems`. It was replaced with `scrapping-bot/data/llm-rande/pattern.json`
(built 2026-08-21), which carries the gate as rule 2's `disqualifies` clause.
No rebuild was needed — that build already existed upstream.

The swap changes what the MODEL IS TOLD, not what is MEASURED: the 78
`signature_tags` are byte-identical between the two, so `tag_signature()`,
`tag_lift` and `signature_tags_carried` are unaffected. The only numeric change
is `knit_share.median`, 0.11215 -> 0.10983. Verdicts written under the old copy
are therefore comparable but were judged against a prompt missing one rule —
re-judge them from the scrape cache rather than trusting the mixture.

    grep -c knit_evidence pattern.json      # 7 = the gate is present, 0 = stale

## Re-syncing

    diff -r scrapping-bot/src/scrapebot   backend/app/prospects/scrapebot
    diff    scrapping-bot/analysis/judge.py backend/app/prospects/analysis/judge.py

Anything other than the import lines listed above is real drift.

## Verifying a change

`tests/test_prospect_assess.py` covers `assess.py` with the network and the
model both injected. To check that the copy still behaves like upstream, score
the same stores through both and compare — `scrapping-bot/data/raw/` holds 711
already-scraped shops, so this needs no network:

    store_payload(domain, store, about, tag_signature(pattern))

was verified identical across 40 of them at the time of copying.
