# In-Form Conflict Warning — Design

**Date:** 2026-07-17 · **Status:** approved
**Builds on:** [`2026-07-17-nearby-conflict-check-design.md`](2026-07-17-nearby-conflict-check-design.md) and `docs/conflict-checker.md`

## Goal

Surface the existing `GET /api/accounts/nearby` conflict check directly in the
wholesale order form: when a sales rep enters a **new** account's store
location, warn immediately (popup) if an existing stockist is too close.
Warning only — it never blocks the order.

## Decisions (confirmed with the user)

1. **Visibility:** the popup appears only when "Filled by" = Sales
   Representative **and** Internal Use → Account = **New**. Customers filling
   the form never see it (the response contains stockist names, which must not
   be exposed to the public).
2. **Trigger:** as soon as the Ship To store address is picked from the Google
   search box — not at submit time. If the conditions become true in any order
   (address first, "new" radio later), the check fires when the last condition
   is met.
3. **Severity:** informational warning only. One dismiss button; submission is
   never blocked.

## Behavior

- A React effect in `App.jsx` watches: `form.representativeOk === true`,
  `internal.accountStatus === 'new'`, and `shipTo.lat`/`shipTo.lng` non-null.
- When all three hold, call `GET /api/accounts/nearby?lat&lng` (server
  defaults: k=5, maxMinutes=20).
- Each coordinate pair is checked **once** (dedupe by `lat,lng` string), so a
  dismissed popup does not reappear for the same address; picking a different
  address re-checks.
- `conflict: true` → show the warning modal. `conflict: false` or API error →
  show nothing (errors log to console only; the form is never disturbed).

### Modal content

- Header: "Possible stockist conflict" + verdict sentence
  ("N existing stockist(s) within a {maxMinutes}-minute drive of this store").
- Evidence table (same columns as `/conflict.html`): store, location, last
  order, miles, drive minutes; conflicting rows highlighted.
- When `mode === "straight-line"` (no server Google key), an approximation
  note is shown.
- Single "OK, got it" button dismisses.

### Same-as-billing fix

`Addresses.jsx` mirrors street/cityState/zip to Ship To when "Same as Bill To"
is ticked, but not lat/lng — so an address searched in the Bill To box never
produced Ship To coordinates. The mirror now includes `lat`/`lng`.

## Files

| File | Change |
|---|---|
| `frontend/src/api.js` | add `getNearbyAccounts(lat, lng)` |
| `frontend/src/components/ConflictWarning.jsx` | new — warning modal |
| `frontend/src/App.jsx` | watch effect + render modal |
| `frontend/src/components/Addresses.jsx` | mirror lat/lng on "Same as Bill To" |
| `frontend/src/index.css` | modal styles |

No backend changes.

## Out of scope / known caveats

- `/api/accounts/nearby` is unauthenticated; hiding the popup from customers
  is UI-level only. If exposure becomes a concern, protect the endpoint like
  `/conflict.html` (basic auth). Recorded in `docs/conflict-checker.md`.
- No submit-time re-check and no persistence of the verdict with the order
  (could be added later if admin wants it recorded).
- Hand-typed addresses (no map search) have no coordinates and are not
  checked — same limitation as documented in `docs/conflict-checker.md`.
