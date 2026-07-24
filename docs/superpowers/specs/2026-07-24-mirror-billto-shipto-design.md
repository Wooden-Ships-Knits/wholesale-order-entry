# Auto-mirror Bill To → Ship To for new customers

**Date:** 2026-07-24
**Component:** `frontend/src/components/Addresses.jsx` (+ one prop from `frontend/src/App.jsx`)

## Problem

New wholesale customers usually ship to the same address they bill to. Today the
form has a manual **"Same as Bill To"** checkbox that mirrors Bill To → Ship To,
but:

1. It starts **unchecked**, so a new customer has to enter their address twice
   (or discover the checkbox).
2. While checked, the Ship To address fields are **disabled** — the customer
   can't tweak them for the common case where shipping differs slightly.

We want new customers to get the Ship To address filled in automatically from
Bill To, while keeping those fields editable.

## Goal

For a **new customer/store**, when they populate the Bill To address, the Ship
To address mirrors it automatically — but the Ship To fields remain editable,
and editing them stops the mirroring.

## Behavior (agreed)

- **Default-on for new customers.** When the account is a new customer
  (`isNewAccount` — the same gate that already controls `showLocationSearch`,
  the Payment section, and Tax Exemption), the "Same as Bill To" box defaults to
  **checked**.
- **Live mirroring while checked.** Ship To Street / City-State / Zip / lat / lng
  track Bill To as it changes — via the existing mirror effect
  (`Addresses.jsx:63-74`), which already handles both account-lookup autofill and
  map-search updates.
- **Fields stay editable.** The `disabled={sameAsBilling}` attribute is removed
  from the three Ship To address inputs. They are never greyed out.
- **Editing unlinks.** Changing a *mirrored* Ship To field — typing in Street /
  City-State / Zip, **or** selecting a place in the Ship To map search — flips
  `sameAsBilling` to `false`. Mirroring stops and the user's edit sticks.
  Re-ticking the box re-syncs everything from Bill To.
- **Non-mirrored fields never unlink.** Editing Ship To **Email** or **Resale
  tax ID** does not affect the checkbox — they are Ship-To-only and never
  mirrored.

## Scope / gating

- Auto-check applies **only to new customers**. Existing accounts (buyer lookup
  autofills both Bill To and Ship To from Salesforce) keep today's behavior: box
  starts unchecked, no auto-mirror.
- **Re-seed rule:** the box auto-checks when the account *becomes* new **only if
  Ship To has no address yet** (`!shipTo.street && !shipTo.cityState &&
  !shipTo.zip`). If the customer already typed a Ship To address, the box is left
  as-is — never overwrite typed data. (Covers a rep who answers the Internal-Use
  radio after the fact.)
- Out of scope: any change to Bill To fields, the buyer lookup, backend
  validation, or the conflict check. Mirroring lat/lng already feeds the conflict
  check correctly and is unchanged.

## Mechanics

1. **New prop `isNewAccount` (boolean) passed from `App.jsx` → `Addresses`.**
   `App.jsx` already computes `isNewAccount` (`App.jsx:188-191`) and passes
   `showLocationSearch={isNewAccount}`. Add `isNewAccount={isNewAccount}` so the
   default-on intent is explicit and independent of the location-search flag.

2. **Seed / re-seed the checkbox.** In `Addresses`, an effect sets
   `sameAsBilling = true` when `isNewAccount` is true **and** Ship To has no
   address yet. It does not force the box off — a user who unticks it stays
   unticked (guard so the effect doesn't re-check on every render; e.g. only act
   on the `isNewAccount` rising edge / empty-Ship-To condition, and don't
   re-run once Ship To is populated).

3. **`unlinkAndSet` helper.** A small wrapper used by the mirrored Ship To
   controls:
   ```js
   const shipEditUnlink = (field, value) => {
     if (sameAsBilling) setSameAsBilling(false)
     setShipTo(field, value)
   }
   ```
   - Street / City-State / Zip `onChange` → `shipEditUnlink(field, v)`.
   - Ship To `AddressMap` `onPlaceSelect` → set `sameAsBilling=false`, then apply
     all place fields (street/cityState/zip/lat/lng).

4. **Remove `disabled={sameAsBilling}`** from the three Ship To address `Field`s
   (`Addresses.jsx:158, 164, 166`).

## Data flow

```
New customer enters Bill To address
  (map search or typed)                → billTo.{street,cityState,zip,lat,lng}
        │  sameAsBilling === true (default for new customer, Ship To empty)
        ▼
mirror effect copies Bill To → Ship To → Ship To address fields reveal, filled
        │
        ├─ user edits a Ship To address field → sameAsBilling=false, edit kept,
        │                                        further Bill To changes ignored
        └─ user re-ticks "Same as Bill To"   → re-sync from Bill To
```

## Testing

Component-level (React Testing Library) or manual via the `verify` skill:

1. **New customer, empty Ship To:** box renders checked; entering a Bill To
   address fills Ship To Street/City-State/Zip identically; fields are editable
   (not disabled).
2. **Edit unlinks:** with the box checked, change Ship To Street → box unchecks,
   the edited value stays, and a subsequent Bill To change does **not** overwrite
   Ship To.
3. **Ship To map search unlinks:** picking a Ship To place with the box checked
   unchecks it and keeps the searched address.
4. **Email / tax ID don't unlink:** editing Ship To Email or Resale tax ID leaves
   the box checked and mirroring active.
5. **Re-tick re-syncs:** re-checking the box copies the current Bill To address
   into Ship To.
6. **Existing account unaffected:** with `isNewAccount` false, box starts
   unchecked; lookup autofill of Ship To is not disturbed.
7. **Re-seed guard:** with a Ship To address already typed, flipping the account
   to "new" does **not** re-check the box or overwrite Ship To.

## Definition of done

- New customer gets Ship To auto-filled from Bill To, fields editable.
- Editing a mirrored Ship To field (or Ship To map search) unlinks; edit persists.
- Existing-account behavior and lat/lng-driven conflict check unchanged.
- Tests above pass.
