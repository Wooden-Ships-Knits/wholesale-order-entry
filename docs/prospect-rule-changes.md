# Changing the scoring rules, and re-assessing what is already scored

The runbook for tuning how a prospect is judged. Written 2026-08-24, after the
first full run (1,381 shops). Read `prospect-scoring-status.md` for what that
run found; this file is only about changing the rules and paying for the
answer again.

**The one number that makes this practical:** re-judging uses the page cache in
`output-dev/prospects/`, so it does not re-fetch anything. Measured on 92 rows:
**1.5 s/row, against 20 s/row for a fresh scrape.**

| | fresh scrape | re-judge from cache |
|---|---|---|
| 1,381 shops | ~7 hours | **~35 minutes** |
| model cost | ~$0.55 | ~$0.55 |

Iterating on rules is cheap. Iterating on the *scraper* is not.

---

## 1. Where the rules live

Four layers. The first two persuade the model; the last two overrule it.

| # | layer | file | when it acts |
|---|---|---|---|
| 1 | Prompt | `backend/app/prospects/analysis/prompt.md` | read at **runtime** |
| 2 | Structured rules | `backend/app/prospects/pattern.json` → `how_to_read_this` | substituted into the prompt |
| 3 | Cheap gate | `backend/app/prospects/analysis/llm_payload.py` → `skip_reason()` | **before** the model, decides `weak` without paying |
| 4 | Answer check | `backend/app/prospects/analysis/judge.py` → `check()` | **after** the model, writes `problems` |

### `prompt.md` is not documentation

`judge.py::_prompt_template()` lifts the text between the ```` fences under
`## System message` and replaces `{contents of pattern.json}`. Editing that
block changes what is sent. Editing anything outside it changes nothing.

Two things will break the run loudly, which is the intent:

- deleting the `{contents of pattern.json}` placeholder → `ValueError`
- renaming the `## System message` heading or removing a fence → `IndexError`

### Layers 3 and 4 cannot be argued with

`skip_reason()` returns `weak` before a model call. `check()` writes `problems`
after one. **No prompt wording overrides either.** If a rule must be absolute,
it belongs in code; if it is a judgement, it belongs in the prompt. Putting an
absolute rule only in the prompt means the model will break it eventually.

---

## 2. The trap: every rule is written twice

The three core questions live in **both** places that reach the model, and they
do not say the same thing:

- `prompt.md` rule 1 — prose, cites `products_per_brand ≈ 9`, `house_brand`
- `pattern.json` rule 1 — thresholds: `max_brands: 3`, `min_catalogue: 200`,
  `unreadable_below_catalogue: 50`

Change one and the model receives two versions of the same rule in one system
message, and picks. **Change both, or neither.**

This is not hypothetical. The copy of `pattern.json` first vendored here did
not mention `knit_evidence` while `judge.check()` enforced it — 83 rows came
back flagged "do not trust this row" for obeying a rule they were never told.

### What must never be hand-edited

`bands_p10_median_p90`, `signature_tags`, `store_type_mix`,
`products_per_brand_p10_median_p90`, `example_accounts`.

These are **measurements** from 242 real account catalogues, not settings.
Inventing a number here compares prospects against customers who do not exist.
To change them, rebuild the artifact:

```bash
cd ~/Automation/scrapping-bot
PYTHONPATH=src python analysis/llm_payload.py data/accounts-l5y.csv data/raw data/llm
cp data/llm/pattern.json ~/Automation/wholesale-order-entry/backend/app/prospects/pattern.json
```

Then check the gate survived the rebuild:

```bash
grep -c knit_evidence backend/app/prospects/pattern.json    # 7 = present, 0 = stale
```

### Vendored-code warning

`prompt.md`, `judge.py`, `llm_payload.py` and everything in `scrapebot/` are
**byte-identical to the `scrapping-bot` repository**. Editing them here creates
drift, and `diff -r` stops being a usable sync check:

```bash
diff -r ~/Automation/scrapping-bot/src/scrapebot   backend/app/prospects/scrapebot
diff    ~/Automation/scrapping-bot/analysis/judge.py backend/app/prospects/analysis/judge.py
```

Decide once, per change: fix it upstream and re-vendor, or edit here and record
the drift in `backend/app/prospects/README.md`. Do not do it silently.

---

## 2b. Changing `extract.py` is a different, heavier job

`scrapebot/extract.py` decides what a *product* is, what counts as *knitwear*,
and what a price is. It does not persuade the model — it changes the numbers the
model is given. Three consequences that a prompt change does not have.

### It silently invalidates the `knit_share` band

`analysis/llm_payload.py` imports `extract` (line 22) and builds
`bands_p10_median_p90.knit_share` from the 242 account catalogues **through the
same code** (line 310).

So editing `KNIT_TERMS` here and re-judging compares prospects measured with the
new vocabulary against a band of accounts measured with the old one. Nothing
errors. Every prospect simply looks more (or less) knit-heavy than our own
customers than it really is, and rules 2 and 3 both read that band.

Measured 2026-08-24 on 60 cached catalogues: adding `"long sleeve"` raised mean
`knitwear_share` by **+1.9 pp** on its own, with the account band unchanged.
Against a band of p10 2.3% / median 11% / p90 22.4%, that is not a rounding
difference.

**So the order is inverted.** A prompt change starts here. An `extract.py`
change starts in `scrapping-bot`:

```bash
cd ~/Automation/scrapping-bot
# 1. make the edit THERE
# 2. rebuild the pattern with the edited extractor
PYTHONPATH=src python analysis/llm_payload.py data/accounts-l5y.csv data/raw data/llm
# 3. vendor BOTH files back, together
cp src/scrapebot/extract.py ~/Automation/wholesale-order-entry/backend/app/prospects/scrapebot/extract.py
cp data/llm/pattern.json    ~/Automation/wholesale-order-entry/backend/app/prospects/pattern.json
```

Copying one without the other is the bug this section exists to prevent.

### The re-judge is wider than a prompt change

A prompt change can only move the 667 rows that reached the model. An
`extract.py` change reaches further, and how far depends on what you touched:

| edited | what moves | re-queue |
|---|---|---|
| `KNIT_TERMS`, `WEAK_KNIT_TERMS`, `NON_SWEATER_TERMS` | knit measurements, and the `skip_reason()` gate | everything except unreadable rows |
| product / price / tag parsing | `catalogue_size`, `products`, prices — including **whether a shop counts as unreadable at all** | everything |

Do not try to be clever. Re-queue all of it:

```sql
UPDATE prospects SET assessed_at = NULL WHERE assessed_at IS NOT NULL;
```

From cache that is ~35 minutes for 1,381 rows. The optimisation is not worth a
silent mismatch.

**No re-fetch is needed.** The cache stores raw HTTP bodies, and extraction runs
fresh on every pass — so an `extract.py` change is re-measured from cache at
full speed.

### It is vendored code

`extract.py` is byte-identical to `scrapping-bot`. Editing it here without going
upstream first breaks `diff -r` as a sync check *and* leaves the pattern stale.
Both, at once. This is the file where "edit here and record the drift" is the
worst of the two options.

### Check the vocabulary before trusting it

`KNIT_RE` is `\b(term)(?:s|ted)?\b` — word-boundary anchored, not substring.
So `cardi` does **not** match `cardigan`; both are needed. And a term that names
a *feature* rather than a *garment* will over-qualify: the file's own opening
comment records that `sweatshirt`, `crewneck`, `poncho`, `jumper` and `shawl`
were each measured against 227k products and cut for exactly that reason.
`"long sleeve"` is the same category of term.

To measure a vocabulary change before adopting it, score cached catalogues under
both lists and compare mean `knitwear_share` and `knit_evidence` flips — no
network, no model calls. That is how the +1.9 pp above was obtained.

---

## 3. The procedure

### Step 1 — change the rule

Edit layer 1 and/or 2 together (see §2). For layers 3 and 4, write a test
first: `backend/tests/test_prospect_assess.py` covers the whole path with the
network and the model both injected, so no key and no socket are needed.

```bash
cd backend && ../venv/bin/python -m pytest tests/test_prospect_assess.py -q
```

### Step 2 — try it on ONE shop before paying for 1,381

`notebooks/assess-one-website.ipynb`. The scrape is cached, so a shop you have
already scored costs only a model call.

**Run §6, not §2.** §2 scores the shop once; §6 scores it N times and shows the
spread. See §4 below for why one run tells you nothing.

### Step 3 — snapshot

Do not skip this. Without it you cannot tell what your change did, and the old
verdicts are gone.

```sql
DROP TABLE IF EXISTS prospects_before;
CREATE TABLE prospects_before AS
  SELECT osm_id, verdict, confidence, for_the_rep, reasons, against,
         problems, knit_evidence, assessed_at
    FROM prospects WHERE assessed_at IS NOT NULL;
SELECT count(*) FROM prospects_before;
```

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev exec -T db \
  psql -U woodenships -d woodenships -v ON_ERROR_STOP=1 -1 -f - <<'SQL'
-- paste the block above
SQL
```

### Step 4 — put the rows back in the queue

`pending()` selects on `assessed_at IS NULL`, so clearing it is what re-queues
a row. Scope it: re-judging one territory is 3 minutes, everything is 35.

```sql
-- everything
UPDATE prospects SET assessed_at = NULL WHERE assessed_at IS NOT NULL;

-- or one territory
UPDATE prospects SET assessed_at = NULL WHERE territory = 'CA/HI - Rande Cohen';

-- or only the rows a PROMPT change can actually move
UPDATE prospects SET assessed_at = NULL
 WHERE for_the_rep IS NOT NULL AND for_the_rep <> ''
   AND for_the_rep NOT LIKE 'Not worth a call:%';
```

That last one is worth knowing, and worth getting exactly right. Of the 1,381
rows scored on 2026-08-22:

| path | rows | can a prompt change move it? |
|---|---|---|
| model answered | 667 | **yes** |
| unreadable site | 700 | no — `_unreadable()`, decided in Python |
| knitwear gate | 14 | no — `_gated()`, decided in Python |

So a prompt-only change needs ~667 rows re-judged (**~17 minutes**), not 1,381.

**The `NOT LIKE` clause matters.** `_gated()` writes
`for_the_rep = "Not worth a call: …"`, which is *not* empty — without that
clause you re-queue 14 rows the model never sees and never will.

This is a string heuristic because **no column records which path a row took**.
That is a real gap: the cheapest fix would be a `decided_by` column
(`model` / `unreadable` / `gate`), which would make this query exact and the
run breakdown in §6 free instead of reconstructed from `reasons` text.

### Step 5 — rebuild, then run

The app code is **not** bind-mounted. An edit on the host does nothing until the
image is rebuilt.

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev build backend
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d backend
```

Then, detached inside the container so a closed terminal cannot kill it:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev exec -d backend sh -c \
  'nohup python -m app.prospects.batch > /output/prospects/rejudge.log 2>&1'
```

Watch it from the host — `/output/prospects/` is bind-mounted to
`output-dev/prospects/`:

```bash
tail -f output-dev/prospects/rejudge.log
```

Options: `--lead "CA/HI - Rande Cohen"` finishes that book first;
`--territory "FL - Jason Hilsenrad"` runs only that one. Territory by territory
is deliberate — an interrupted run leaves finished books rather than twelve
unusable halves. Rows commit one at a time, so nothing already paid for is lost.

Safe to re-run: anything with `assessed_at` is skipped.

### Step 6 — compare

```sql
SELECT s.verdict AS before, p.verdict AS after, count(*)
  FROM prospects p JOIN prospects_before s USING (osm_id)
 WHERE p.verdict IS DISTINCT FROM s.verdict
 GROUP BY 1, 2 ORDER BY 3 DESC;
```

And the flagged-answer count, which is the health signal:

```sql
SELECT count(*) FILTER (WHERE problems <> '') AS flagged, count(*) AS assessed
  FROM prospects WHERE assessed_at IS NOT NULL;
```

Rising `flagged` means the model is being held to a rule it was not told — go
back to §2.

---

## 4. Read the result honestly

**The model is not deterministic, even at `temperature=0`.** Measured
2026-08-22: lspace.com, the same cached catalogue and the same pattern, five
runs → `possible` ×4, `weak` ×1. Shops near a rule boundary flip on their own.

So a diff of "31 verdicts moved out of 1,381" after a prompt change is **not
evidence the change did anything**. It is inside the noise. This already
misled us once: the `pattern.json` swap on 2026-08-22 was reported as
"exactly 2 verdicts moved, verified" — it was not verified, it was noise.

To actually measure a change:

1. Pick 5–10 shops that sit near the boundary you are moving (`possible` and
   `weak` with `confidence: medium` are the ones that flip).
2. Notebook §6, N=5, **before** the change. Record the spread.
3. Make the change, rebuild, run §6 again on the same shops.
4. 5/5 `weak` → 5/5 `possible` is signal. 4/5 → 3/5 is not.

Nothing currently stores how stable a verdict is: a shop that scores 5/5 `weak`
and one that scores 3/5 `weak` are written to the row identically. Fixing that
means scoring N times and storing the spread, at N× the model cost.

---

## 5. Pushing the result to the VM

Local first, always — the VM is where reviewers look, not where you experiment.
When the local numbers are right:

```bash
# on the laptop, build an upsert-safe sync file (see the recipe in
# prospect-scoring-status.md), then:
gzip -kf ~/prospects-sync-<date>.sql
gcloud storage cp ~/prospects-sync-<date>.sql.gz \
  gs://automation-project-500308_cloudbuild/ --project=automation-project-500308
```

```bash
# on the VM
gcloud storage cp gs://automation-project-500308_cloudbuild/prospects-sync-<date>.sql.gz ~/
gunzip -f ~/prospects-sync-<date>.sql.gz
ls -lh ~/prospects-sync-<date>.sql          # confirm it landed BEFORE the next line
docker compose -f docker-compose.dev.yml --env-file .env.dev exec -T db \
  psql -U woodenships -d woodenships -q -v ON_ERROR_STOP=1 < ~/prospects-sync-<date>.sql
```

Use an **upsert via a staging table**, never `TRUNCATE`: `prospect_marks` holds
each rep's shortlist and points at `prospects.id`, so reassigning ids orphans
their stars. The sync file must never write `id` or `first_seen_at`.

Delete the object from the bucket afterwards — it is a shared Cloud Build
bucket and the file is 1,437 shop records.

The VM code must be at the same commit, or the restore fails on missing
columns:

```bash
docker compose -f docker-compose.dev.yml --env-file .env.dev exec -T db \
  psql -U woodenships -d woodenships -c "select version_num from alembic_version;"
```

---

## 6. Checklist

- [ ] Rule changed in **both** `prompt.md` and `pattern.json` (§2)
- [ ] If `extract.py` was touched: edited in `scrapping-bot` FIRST, pattern
      rebuilt there, and **both files vendored back together** (§2b)
- [ ] If `extract.py` was touched: **all** rows re-queued, not just the 667 (§2b)
- [ ] Absolute rules in code, judgements in the prompt (§1)
- [ ] Vendored drift decided and recorded (§2)
- [ ] Tests pass: `pytest tests/test_prospect_assess.py`
- [ ] Tried on one shop with notebook **§6**, not §2 (§4)
- [ ] `prospects_before` snapshot taken (§3)
- [ ] `assessed_at` cleared only where the change can reach (§3)
- [ ] **Image rebuilt** — the app code is not bind-mounted (§3)
- [ ] Run detached; log at `output-dev/prospects/rejudge.log`
- [ ] Diff reviewed, and read against the noise floor (§4, §6)
- [ ] `problems` count did not rise (§3)
