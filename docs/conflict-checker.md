# Conflict Checker — Nearby-Stockist Check for New Customers

**Endpoint:** `GET /api/accounts/nearby` · **Added:** 2026-07-17 · **Tool page:** `/admin` → *Conflict check* tab
Design spec: [`superpowers/specs/2026-07-17-nearby-conflict-check-design.md`](superpowers/specs/2026-07-17-nearby-conflict-check-design.md)

## What it does

When a **new customer** (someone not found in Salesforce) fills the wholesale order form, Wooden Ships wants to know:

> *"Is there already a store selling Wooden Ships too close to this new store?"*

This is brand protection: two stockists on the same street compete for the same shoppers. The conflict checker answers that question with data instead of memory.

**The rule: a conflict exists when an existing wholesale account is less than a 20-minute drive from the new customer's store.**

Drive time is used instead of straight-line distance on purpose — two stores 2 miles apart across a river can be a 40-minute drive from each other, while 10 miles down one highway can be 12 minutes. Twenty minutes of driving is what "same shopping area" actually means to a customer.

## The admin tool page

Sign in at `https://<site>/admin` and pick the **Conflict check** tab: type a location in the Google search box, pick a suggestion, and it shows the verdict banner plus the nearest-stockists table. The drive-time threshold and how many neighbors to show are adjustable on the page.

It lives inside the admin app (`frontend/src/conflict/ConflictCheck.jsx`, rendered by `frontend/src/admin/AdminApp.jsx` with the `embedded` prop), so it is behind the admin password — which matters, because it exposes the stockist list. The old standalone URLs `/check-conflict` and `/conflict.html` 301 to `/admin` (see `frontend/nginx.conf`); no separate basic auth is needed.

Note the API itself, `GET /api/accounts/nearby`, stays unauthenticated — the order form calls it for the rep-only warning modal, where it returns no stockist names.


## The conflict email draft

`POST /api/conflict-email` (admin-only) returns `{to, subject, body}` — a polite "we already have a stockist serving this area" letter addressed to the applicant. It **sends nothing**: the admin reviews and edits it in a popup, then copies it or opens it in their own mail client (`mailto:`). No SMTP configuration is involved.

Two call sites, both in `/admin`:

| Page | Trigger | Payload |
|---|---|---|
| Orders table | *Generate email* button, shown only on rows where `hasConflict` is true | `{orderId}` — buyer name, contact, email, ship address and rep come from the order |
| Conflict check tab | *Generate email* button, shown only when the verdict is CONFLICT | `{address, maxMinutes}` — there is no order yet, so the user fills the recipient in the popup |

Any explicit field overrides what the order supplied, so the same endpoint serves both. The body never names the neighboring stockists: it is addressed to the applicant, and who else stocks the brand is internal. Wording lives in `backend/app/email/conflict_template.py`; the popup is `frontend/src/components/EmailDraftModal.jsx`.

## How to call it

```
GET /api/accounts/nearby?lat=41.8781&lng=-87.6298
```

| Parameter | Required | Default | Meaning |
|---|---|---|---|
| `lat` | yes | — | Latitude of the new customer's **Ship To** store location (−90…90) |
| `lng` | yes | — | Longitude (−180…180) |
| `k` | no | 5 | How many nearest stores to return (1…25) |
| `maxMinutes` | no | 20 | Conflict threshold in driving minutes (1…240) |

The `lat`/`lng` come free from the order form: when the buyer picks their address with the Google Maps search box, the form captures the coordinates.

### Example response

```json
{
  "conflict": true,
  "mode": "drive-time",
  "maxMinutes": 20,
  "neighbors": [
    {
      "accountId": "001GC00003jfHTNYA2",
      "name": "A PIED",
      "cityState": "Chicago, IL",
      "lastOrder": "2024-11-08",
      "distanceMiles": 3.6,
      "driveMinutes": 10
    },
    {
      "accountId": "00190000009HHnXAAW",
      "name": "CINNAMON BOUTIQUE",
      "cityState": "Chicago, IL",
      "lastOrder": "2023-09-15",
      "distanceMiles": 5.2,
      "driveMinutes": 16
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `conflict` | `true` if **any** neighbor is closer than `maxMinutes` of driving. This is the yes/no answer. |
| `mode` | `"drive-time"` (normal) or `"straight-line"` (fallback — see below) |
| `maxMinutes` | The threshold that was applied |
| `neighbors` | The k nearest existing wholesale stores, closest first — the **evidence** behind the verdict, ready to show in any future review UI |
| `driveMinutes` | Real driving time from Google; `null` if Google couldn't route it (or in fallback mode) |
| `lastOrder` | Date of that store's most recent sales order (what qualifies it as an active stockist) |

Bad input (latitude 123, missing `lng`, `k` = 0 …) returns a standard `422` validation error.

## How it works inside

```mermaid
flowchart LR
    A[lat / lng of new store] --> B[Salesforce:\nwholesale accounts, geocoded,\nordered in last 3 years ~900\ncached 5 min]
    B --> C[Haversine distance\nin Python — keep\nnearest 10–25]
    C --> D[Google Distance Matrix\n1 request → driving minutes]
    D --> E{any neighbor\n< maxMinutes?}
    E -->|yes| F[conflict: true]
    E -->|no| G[conflict: false]
```

1. **Candidate set** — Salesforce accounts with `Type = 'Wholesale'`, a shipping geocode, **at least one sales order in the last 3 years** (`CONFLICT_ORDER_YEARS`, decision 2026-07-17 — a store that hasn't ordered in 3 years isn't an active stockist), **and a `Rank__c` that isn't excluded** (decision 2026-07-18: `ZZ - No Booking`, `Z - Inactive`, `E - No Marketing`, `X - Conflict`, `OOB - Out of Business` never count; accounts with no rank still do). That's ~820 accounts, out of ~4,400 geocoded wholesale accounts. Salesforce geocodes shipping addresses automatically, so we maintain no coordinates ourselves. The list is cached for 5 minutes like the other Salesforce lookups.
2. **Pre-filter** — straight-line (haversine) distance to every candidate, keep the nearest 10–25. This is exact math over a few thousand points; it takes milliseconds and costs nothing.
3. **Drive times** — one Google Distance Matrix request for just those finalists (25 is Google's per-request limit — which is why the pre-filter exists). Only raw coordinates are sent to Google, never store names or Salesforce ids.
4. **Verdict** — sort by drive time, return the top `k`, and flag `conflict` if anything is under the threshold.

## The two modes

| | `drive-time` | `straight-line` |
|---|---|---|
| When | `GOOGLE_MAPS_SERVER_API_KEY` is configured and Google responds | Key missing, or Google errored/timed out |
| `driveMinutes` | real minutes | always `null` |
| Conflict rule | drive < `maxMinutes` | distance < `maxMinutes × 0.5` miles (assumes 30 mph, so 20 min ≈ 10 miles) |

The endpoint **never fails because Google is down** — it degrades to straight-line mode and says so in `mode`, so a caller can always distinguish an approximate verdict from a real one.

> **Current state:** the server key is configured — the API returns real drive times (`mode: "drive-time"`, verified 2026-07-17).

## Setup: enabling real drive times

1. In Google Cloud console, create a **new API key** (do not reuse the browser key from `frontend/.env` — that one is referrer-restricted and public).
2. Restrict the new key: **IP restriction** to the GCP VM, API restriction to **Distance Matrix API** only.
3. In the backend `.env`:
   ```
   GOOGLE_MAPS_SERVER_API_KEY=<the new key>
   CONFLICT_MAX_MINUTES=20        # optional, this is the default
   ```
4. `docker compose up -d backend` to restart.

**Cost:** about $5 per 1,000 destination lookups → ~10 destinations per check ≈ **$0.05 per new-customer check**. It only runs when someone calls the endpoint.

## Where the code lives

| Piece | File |
|---|---|
| Route + parameter validation | `backend/app/routers/accounts.py` (`nearby_accounts`) |
| Haversine + nearest-candidate selection | `backend/app/geo/distance.py` |
| Google Distance Matrix client | `backend/app/geo/drive_time.py` |
| Orchestration, fallback, verdict | `backend/app/geo/conflict.py` |
| Salesforce query + field names | `backend/app/salesforce/client.py`, `mapping.py` |
| Config | `backend/app/config.py`, `.env.example` |
| Tests (28 total incl. this feature) | `backend/tests/test_geo_distance.py`, `test_drive_time.py`, `test_conflict.py`, `test_nearby_endpoint.py` |

## Known limitations / open decisions

- ~~Closed stores count as stockists~~ — **RESOLVED 2026-07-17** by the order-history filter: candidates must have ordered within the last 3 years, and none of the 267 "(CLOSED)"-named accounts have (verified against the org). Tune the window with `CONFLICT_ORDER_YEARS`.
- ~~Where the check surfaces is undecided~~ — **RESOLVED 2026-07-17**: the check is wired into the order form. When "Filled by" = Sales Representative, Internal Use → Account = New, and the Ship To address has coordinates from the map search, the form calls this endpoint and shows a dismissible warning modal on `conflict: true` (`frontend/src/components/ConflictWarning.jsx`). Warning only — it never blocks submission, and customers filling the form never see it (the response exposes stockist names). Design: [`superpowers/specs/2026-07-17-in-form-conflict-warning-design.md`](superpowers/specs/2026-07-17-in-form-conflict-warning-design.md).
- **New-customer coordinates are required.** If a buyer types their address by hand instead of using the map search, there are no coordinates to check. A future improvement could geocode the typed address server-side.
- Salesforce data is cached for 5 minutes, so an account created seconds ago may not appear immediately.
