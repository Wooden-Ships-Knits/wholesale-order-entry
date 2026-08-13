# Prospecting: finding new stockists inside a territory

Status: **plan, not built.** Test territory throughout: `FL - Jason Hilsenrad`.

## The goal

Find shops in a rep's territory that could stock Wooden Ships and do not
already, and hand the rep a list that is worth their time — each row already
answered for "would this clash with a store we already sell to?".

## Step 1 output

One row per candidate shop:

| column | type | source |
|---|---|---|
| `store_name` | str | discovery |
| `latitude`, `longitude` | float | discovery |
| `website` | str \| null | discovery |
| `potential_conflict` | bool | our existing conflict check |
| *(working)* `place_id`, `address`, `nearest_stockist`, `drive_minutes` | | kept for review |

The last four are not in the brief but are what make the boolean auditable — a
bare `True` nobody can check is a number nobody will act on.

---

## What already exists — do not rebuild it

**The conflict rule is written and in production.** `app/geo/conflict.py::find_nearby(lat, lng, k, max_minutes)`
returns the k nearest wholesale stockists and a verdict. A neighbour closer than
`CONFLICT_MAX_MINUTES` (20) by driving time is a conflict; without a server-side
Google key it degrades to straight-line distance. Only accounts that ordered
within `CONFLICT_ORDER_YEARS` (3) count, and `EXCLUDED_RANKS` (inactive, OOB,
no-marketing…) never count. See `docs/conflict-checker.md`.

So `potential_conflict` is one call per candidate. Reusing it also means the
prospecting list and the live order form can never disagree about what a
conflict is — if they disagreed, the rep would chase a lead the form later
rejects.

**Territory → geography** is `sheets/client.py::territory_for_state()`, reading
the REGION tab (state code → territory label). That is the only mapping we have.

**Existing stockists** are Salesforce Accounts filtered on `SalesTerritory__c`;
`notebooks/territory_map.py` already fetches and maps them.

---

## The three problems to solve, in order

### 1. A territory is a label, not a shape

`FL - Jason Hilsenrad` has no boundary. REGION maps *states* to territories, so
the coarse answer is "the states that map to this territory" — but the live
data shows the territory holds 140 Florida accounts **and one in Georgia**, so
state is an approximation, not a definition.

Options, cheapest first:

- **Search around existing stockists.** Take the 138 geocoded accounts, search a
  radius around each. Finds shops in the areas the rep already works — which is
  also where a conflict is most likely, so it is the least useful ground.
- **Search around population centres.** A list of FL cities above some
  population, searched independently of where we already sell. Finds white
  space, which is the point.
- **Grid the state.** Even coverage, most API calls, most duplicates.

Start with population centres; it is the only one that answers "where are we
absent?".

### 2. Discovery: use Places, not a crawler

The brief says "crawling, potentially use a bot". **Prefer the Google Places
API** for the first pass:

- We already hold `GOOGLE_MAPS_SERVER_API_KEY` for Distance Matrix, so the
  billing account and IP restriction exist.
- Places returns exactly the fields Step 1 wants — name, lat/lng, website,
  address — already structured, already geocoded. A crawler would have to
  geocode addresses itself, which is another paid API call and another source of
  error.
- It is within terms of service. Scraping a retailer directory or Google's
  result pages is not, and a blocked IP or a legal complaint costs more than the
  API ever will.

`Nearby Search` with `type=clothing_store` plus keyword terms ("boutique",
"women's clothing", "sweaters"), then `Place Details` for the website.

**Where a crawler does earn its place: step 2, not step 1.** Places tells you a
shop exists; it cannot tell you whether it sells women's knitwear at Wooden
Ships' price point. Fetching each candidate's own website and looking for
signals (brands carried, "sweater"/"knitwear", price range, wholesale/stockist
pages) is the qualifying pass — and that is a small, polite fetch of one page
per candidate, honouring `robots.txt`, not a broad crawl.

### 3. Do not "discover" our own customers

Every candidate must be checked against the Salesforce accounts we already have,
before the rep ever sees it. Name matching alone is unreliable (`MORLEY(DELRAY
BEACH)` vs `Morley`), so match on **both**: normalised name similarity *and*
proximity — a candidate within ~100 m of an existing account is almost certainly
that account.

---

## Pipeline

```
territory ──► states (REGION tab)
                │
                ▼
        search origins (city centres)
                │
                ▼   Google Places Nearby Search
        raw candidates (name, lat/lng, place_id)
                │
                ├─► drop: already a Salesforce account (name + proximity)
                │
                ▼   Place Details
        + website, address, categories
                │
                ▼   app/geo/conflict.py::find_nearby
        + potential_conflict, nearest_stockist, drive_minutes
                │
                ▼
        Step 1 table  ──►  (step 2) qualify from the shop's own website
```

## Build order

1. **Origins** — territory → states → city list. Hardcode a dozen FL cities to
   start; a population source can come later.
2. **One Places call, one city**, printed raw. Confirms key, quota and the
   fields that actually come back before anything is built on top.
3. **Dedupe against Salesforce.** Run it against the 141 known FL accounts and
   check it recognises them — if it cannot find stores we *know* are there, the
   matching is wrong and every later number is inflated.
4. **Conflict column** via the existing `find_nearby`.
5. **Export** — CSV next to the other notebook outputs, plus a folium map reusing
   `territory_map.plot()` so candidates and stockists can be seen together.
6. *(step 2)* Website qualification.

Stop after 3 and look at the output. If dedupe is weak, everything downstream is
noise, and that is cheaper to find out at 141 rows than at 2,000.

## Costs and limits worth knowing before starting

- **Places is billed per request**, and `Place Details` is a second call per
  candidate. A dozen cities × 20 results × 2 calls is small; a state-wide grid is
  not. Cache by `place_id` — candidates repeat heavily between nearby origins.
- **Nearby Search returns 20 per page, 60 maximum** per origin. More origins,
  not bigger radii.
- **`find_nearby` calls Distance Matrix** — also billed, also per candidate. Run
  the cheap filters (dedupe) *before* the conflict check, not after.
- The 3 FL accounts with no geocode are invisible to proximity dedupe and to the
  conflict check. They will produce false "no conflict" answers. Listed in
  `territory_map.plot()`'s output.

## Open questions

- What qualifies a shop as a real prospect — is there a rank, size or brand
  signal the team already uses by eye?
- Does a candidate inside the 20-minute radius get dropped, or shown flagged?
  Dropping hides genuine opportunities the team might still want (a conflict is
  a judgement call — that is why the rep is asked, not told).
- Who reviews the output, and where does it live? A CSV, a tab in the admin
  page, or a Google Sheet the reps already open?
