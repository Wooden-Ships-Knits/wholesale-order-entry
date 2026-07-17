# Nearby-Stockist Conflict Check API — Design

**Date:** 2026-07-17 · **Status:** approved (webadmin)
**Scope:** backend only — no frontend changes; the consuming UI is undecided.

## Problem

When a new customer (no Salesforce match) fills the wholesale order form, Wooden Ships wants to know whether an existing wholesale stockist is too close to the new store — brand protection. "Too close" is defined by **driving time: under 20 minutes** (not straight-line distance).

## Decisions (from design discussion)

- Conflict source point: the new customer's **Ship To** location — lat/lng captured by the form's Google Places search.
- Comparison set: Salesforce `Account` where `Type = 'Wholesale'` and shipping geocode present. Verified against the org 2026-07-17: 6,467 accounts; 4,930 have `ShippingLatitude` (Salesforce auto-geocode, accuracy `Address`/`NearAddress`); 4,395 of those are `Type = 'Wholesale'`. `BillingLatitude` is unpopulated org-wide — shipping coordinates are the only usable geocodes.
- API returns **both** the evidence (K nearest neighbors with distances/drive times) **and** a conflict verdict, so a yes/no consumer and a review UI are both served.
- Threshold default 20 minutes, overridable per request; server default configurable via env.

## API

`GET /api/accounts/nearby`

| Param | Type | Default | Constraints |
|---|---|---|---|
| `lat` | float | required | −90…90 |
| `lng` | float | required | −180…180 |
| `k` | int | 5 | 1…25 |
| `maxMinutes` | int | `CONFLICT_MAX_MINUTES` (20) | 1…240 |

Response `200`:

```json
{
  "conflict": true,
  "mode": "drive-time",
  "maxMinutes": 20,
  "neighbors": [
    { "accountId": "001…", "name": "Lakeview Knits", "cityState": "Chicago, IL",
      "distanceMiles": 2.4, "driveMinutes": 9 }
  ]
}
```

- `mode` is `"drive-time"` normally, `"straight-line"` when the Google key is missing or the Distance Matrix call fails (never a 500 for Google flakiness).
- In straight-line mode `driveMinutes` is `null` and conflict uses `maxMinutes × 0.5` miles (30 mph approximation, constant `APPROX_MILES_PER_MINUTE = 0.5`).
- Invalid params → FastAPI 422. Salesforce failure → propagates like the other lookup endpoints.

## Data flow

1. `salesforce/client.list_geocoded_wholesale_accounts()` — SOQL on `Account` (`Type='Wholesale' AND ShippingLatitude != null AND ShippingLongitude != null`), fields via `mapping.NEARBY_ACCOUNT_FIELDS`, cached with the existing 5-minute `_cached` helper (~4.4k rows).
2. `geo/distance.py` — pure-Python haversine; select the nearest `min(max(k, 10), 25)` candidates (25 = Distance Matrix per-request destination limit). Exact KNN over 4.4k points; no ML dependency.
3. `geo/drive_time.py` — one Google Distance Matrix request (`requests`, 5 s timeout, `mode=driving`) → minutes per candidate; unreachable elements → `null`. Isolated module so a future move to the Routes API is a one-file change.
4. `geo/conflict.py` — orchestrates 1–3, sorts by drive minutes (straight-line distance in fallback mode), truncates to `k`, computes `conflict`.
5. Route added to `routers/accounts.py` (kept thin per house rules).

## Configuration

- `GOOGLE_MAPS_SERVER_API_KEY` — **separate from the browser key**; IP-restricted, Distance Matrix API only, never reaches the client. Empty ⇒ straight-line mode.
- `CONFLICT_MAX_MINUTES` — default 20.
- Both in `backend` `.env` / `.env.example` and `config.py` (pydantic-settings).

## Security & cost

- Only raw coordinates go to Google — no names, no Salesforce identifiers.
- ~10 destinations per check ≈ $0.05 (Distance Matrix pricing); triggered only for new-customer checks.
- Rate limiting: same future-work note as the other lookup endpoints (architecture.md §9).

## Testing

- `tests/test_geo_distance.py` — haversine against known city pairs; candidate selection order/pool size.
- `tests/test_drive_time.py` — Distance Matrix JSON parsing, element failures, HTTP/status errors (mocked `requests`).
- `tests/test_conflict.py` — drive-time mode verdicts, fallback on missing key and on Google error, sorting, `k` truncation (Salesforce + Google monkeypatched).
- Endpoint test with FastAPI `TestClient` (adds `httpx` to dev requirements).

## Out of scope

- Frontend integration (UI undecided), order-submit integration, persistence of check results, and any Salesforce writes.
