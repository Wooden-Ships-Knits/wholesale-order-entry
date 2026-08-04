# PO # as a Shared (Customer or Rep) Field — Design

**Date:** 2026-08-04 · **Status:** approved

## Goal

Let **either** a customer or a sales rep enter a PO number. Today the field is
inside the Internal Use section, which only mounts when "Filled by" = Sales
Representative, so a customer filling the form has no way to supply their own
purchase-order number.

Move it out of Internal Use and into the order header, immediately right of
"Filled by", where both audiences see it.

## Decisions (confirmed with the user)

1. **Placement:** the header grid's currently empty middle cell on row 1 —
   directly to the right of the "Filled by" radios.
2. **PDF:** PO # moves to the header meta row on both templates and is removed
   from the INTERNAL USE ONLY block. The PDFs then mirror the web form.
3. **Payload shape:** `po_number` is promoted from the `Internal` model to a
   top-level field on `OrderSubmission`.
4. **Optionality is unchanged** — PO # stays optional for everyone. No new
   validation, client or server.

## Current state

| Concern | Location |
|---|---|
| React state | `frontend/src/App.jsx:83` — `poNumber: ''` inside the `internal` object |
| Input | `frontend/src/components/InternalUse.jsx:111-114` |
| Section gating | `frontend/src/App.jsx:373` — `<InternalUse>` renders only when `form.representativeOk === true` |
| Header grid | `frontend/src/index.css:67-93` — `grid-template-areas: 'filled . total' / 'date season ship'` |
| Request schema | `backend/app/schemas/order.py:110` — `Internal.po_number` |
| Persistence | `backend/app/routers/orders.py:251` — `po_number=payload.internal.po_number` |
| PDF context | `backend/app/routers/orders.py:307` — `"po_number": order.po_number` |
| Customer/admin PDF | `backend/app/pdf/template.html:263` (internal-use table) |
| Init-form PDF | `backend/app/pdf/template_init.html:167` (internal-use table) |
| DB column | `orders.po_number text` — `backend/app/db/models.py:92` |

Note that `internal` is submitted on every order regardless of who filled the
form, so the *data path* already works for customers. The problem is purely
that the input is never rendered for them — plus the semantic mismatch of a
customer-facing value living in a model named `Internal`.

## Changes

### 1. Frontend — header input

`frontend/src/components/OrderHeader.jsx`

Add, between the `ha-filled` fieldset and the `ha-total` div:

```jsx
<label className="ha-po">
  PO # (optional)
  <input
    type="text"
    value={form.poNumber}
    onChange={(e) => setField('poNumber', e.target.value)}
  />
</label>
```

`frontend/src/index.css`

- Row 1 of `.header-grid` becomes `'filled po total'` (replacing the `.`
  placeholder at line 71).
- Add `.ha-po { grid-area: po; }`.
- **Add `.ha-po` to the `grid-area: auto` reset list at lines 661-667.** The
  existing comment there explains why: with `grid-template-areas: none`, a
  `grid-area` naming a line that no longer exists resolves against implicit
  lines and stacks every child into one cell. Omitting `.ha-po` there would
  draw the PO field on top of the other header fields on screens ≤720px.

### 2. Frontend — remove from Internal Use

`frontend/src/components/InternalUse.jsx` — delete the `PO # (optional)` label
block (lines 111-114). Nothing else in that component references `poNumber`.

### 3. Frontend — state

`frontend/src/App.jsx`

- Remove `poNumber: ''` from the `internal` initial state (line 83).
- Add `poNumber: ''` to the `form` initial state (lines 51-62).
- Add `poNumber: form.poNumber` to the submit payload (the object built at
  line 303), alongside the other top-level header fields.

No change to the submit validation block (lines 251-276) — the field is
optional.

### 4. Backend — schema

`backend/app/schemas/order.py`

- Remove `po_number: str = ""` from `Internal` (line 110).
- Add `po_number: str = ""` to `OrderSubmission`, near the other header fields
  (`ship_window`, `filled_by`).

`CamelModel` handles the `poNumber` ⇄ `po_number` aliasing, same as every
other field.

### 5. Backend — persistence

`backend/app/routers/orders.py:251` — `po_number=payload.internal.po_number`
becomes `po_number=payload.po_number`. Move the line up beside the other
header assignments rather than leaving it among the `payload.internal.*` group.

`pdf_context` (line 307) is unchanged — the key stays `order.po_number`.

### 6. PDF templates

Both templates use fixed-column tables, so every cell added or removed must be
balanced by a `colspan` on the opposite row or the columns visibly misalign.

`backend/app/pdf/template.html` — masthead table (lines 85-128)

Row 1 is `logo(rowspan 2) | Contact | Ship window | Order date | Order total |
season(rowspan 2)`; row 2 is `Order ref | Filled by | Payment by | Charge
approval` — 4 middle cells each.

- Insert a `PO #` cell into row 2 immediately after `Filled by`, giving row 2
  five middle cells.
- Rebalance by putting `colspan="2"` on the row-1 `Contact` cell (line 90).
  That address is the longest string in the row, so the extra width helps it
  rather than stranding whitespace.

`backend/app/pdf/template.html` — INTERNAL USE ONLY table (lines 254-268)

Row 1 is `internal-bar(rowspan 2) | New or reorder | New account/existing |
Campaign(colspan 2)` — 4 middle columns; row 2 is `PO # | Rep | Order written
by | Split`.

- Delete the `PO #` cell (line 263).
- Rebalance by putting `colspan="2"` on the row-2 `Split` cell.

`backend/app/pdf/template_init.html`

- `.meta` table (lines 43-52): add a `PO #` cell after `Filled by`. This is a
  single-row table, so no rebalancing is needed — it goes from 6 cells to 7.
- Internal Use table (lines 158-172): delete the `PO #` cell from row 1
  (line 167), then put `colspan="2"` on the row-1 `Campaign` cell so row 1
  still matches row 2's four cells.

### 7. Database

**No migration.** The `orders.po_number` column already exists
(`0001_orders.py:55`) and is unchanged. Only the request-body shape moves.

### 8. Docs

- `docs/PRD.md` §5.1 (Order header) — add a PO # bullet noting it is optional
  and available to both customers and reps, dated 2026-08-04.
- `docs/PRD.md` §5.9 (Internal Use) — remove the `PO # (optional)` bullet.
- `docs/architecture.md:174` — move the `po_number` line out of the
  `-- internal use` comment group into the header-field group above it.

## Testing

**Backend:** add a case to `backend/tests/test_order_schema.py` asserting that a
customer-filled payload (`filledBy: "customer"`, no `internal` block) carrying a
top-level `poNumber` round-trips into `OrderSubmission.po_number`. This is the
regression that matters — it is exactly the path that was impossible before.

**Frontend:** no test suite exists in `frontend/`, so verify at runtime with the
`verify` skill:

1. Load the form as a **customer** ("Filled by" = Customer) — PO # is visible
   and editable, Internal Use stays hidden.
2. Switch to **Sales Representative** — PO # stays in the header and does *not*
   reappear inside Internal Use.
3. Narrow the viewport below 720px — the header stacks cleanly with no
   overlapping fields.

## Out of scope

- Salesforce sync for `po_number` (`salesforce/mapping.py` does not map it
  today and this change does not add it).
- Any admin-page display of PO # (the admin order table does not show it today).
- Length limits or format validation on the PO number.
