# "Filled by" Gate Before the Order Form — Design

**Date:** 2026-08-05 · **Status:** approved

## Goal

Require an answer to **"Filled by"** before any of the order form is shown.

The form's shape depends on that answer: Internal Use mounts only for a rep,
Terms/Signature mounts only for a customer, and the submit button changes
wording. Until the question is answered (`representativeOk === null`) the form
still renders — in a *customer-shaped* layout, because every gate in `App.jsx`
tests for `=== true` or `=== false` and `null` falls through to the customer
branch. A rep therefore starts filling in the wrong layout, and sections appear
and disappear underneath them the moment they answer.

Show one question first. Render the form only once it has an answer.

## Decisions (confirmed with the user)

1. **One URL for everyone.** No `/order_form/rep` variant, no query parameter,
   no remembered choice in `localStorage`. Rep and customer open the same link
   and both answer the question.
2. **The gate asks only "Filled by".** The customer's follow-up "Is this your
   first order with Wooden Ships?" stays where it is in the order header
   (`OrderHeader.jsx:99-123`) and keeps driving Payment / Tax Exemption /
   location search from there. The gate is deliberately not a wizard.
3. **The answer stays changeable.** ~~The "Filled by" radios remain in the
   order header, editable, exactly as today.~~ **Superseded 2026-08-05** — see
   the amendment below: the radios are gone and a Back button returns to the
   gate instead. The principle holds: the gate prevents *starting* without an
   answer, it does not lock the answer in.
4. **A full-screen step, not a modal.** Rejected: an overlay above the form,
   because the form behind it is by definition in the wrong shape — it would
   preview a layout the user is about to invalidate — and it would need focus
   trapping and scroll locking to be usable. Rejected: separate routes per
   role, which conflicts with decisions 1 and 3 (the URL and the radio could
   disagree).

## Current state

| Concern | Location |
|---|---|
| React state | `frontend/src/App.jsx:51-65` — `representativeOk: null` inside `form` |
| The radios | `frontend/src/components/OrderHeader.jsx:18-40` |
| Rep-only section | `frontend/src/App.jsx:402-411` — `<InternalUse>` renders when `representativeOk === true` |
| Customer-only section | `frontend/src/App.jsx:477-479` — `<TermsSignature>` renders when `!isRepFilled` |
| Derived: rep-filled | `frontend/src/App.jsx:192` — `isRepFilled = form.representativeOk === true` |
| Derived: new account | `frontend/src/App.jsx:197-200` |
| Submit validation | `frontend/src/App.jsx:267` — `'Please select who is filling in this form.'` |
| Payload | `frontend/src/App.jsx:324` — `filledBy: … 'rep' : … 'customer' : ''` |
| Existing early return | `frontend/src/App.jsx:374-387` — the post-submit confirmation |
| Logo markup to reuse | `frontend/src/components/OrderHeader.jsx:12-14` (`.brand` / `.brand-logo`) |

## Changes

### 1. New component — `frontend/src/components/FilledByGate.jsx`

A presentational component with a single prop, `onChoose(bool)`. It holds no
state of its own.

```jsx
export default function FilledByGate({ onChoose }) {
  return (
    <main className="order-form filled-by-gate">
      <div className="brand">
        <img src="/ws-logo-black.png" alt="Wooden Ships — Paola Buendia" className="brand-logo" />
      </div>
      <h1 className="gate-question">Hi! Who is filling out this order form?</h1>
      <div className="gate-choices">
        <button type="button" onClick={() => onChoose(true)}>Sales Representative</button>
        <button type="button" onClick={() => onChoose(false)}>Customer</button>
      </div>
    </main>
  )
}
```

Notes on the markup:

- `<main>`, not `<form>` — the gate replaces the form entirely rather than
  nesting inside it.
- Real `<button>` elements, so keyboard tab and enter work without any extra
  code. No `role`/`tabIndex`/`onKeyDown` handling to write.
- The choice submits itself. No "Continue" button: a second click would add
  nothing, and the answer is changeable afterwards anyway (decision 3).
- The logo is the same asset and classes the order header already uses, so the
  first screen matches the form the user is about to see.
- The greeting and the question share one line — **"Hi! Who is filling out
  this order form?"** — because opening on "Who…" read colder than it needed
  to (added 2026-08-05). It is the page's only heading, so it is an `<h1>`
  styled as one, not a caption.

### 2. `frontend/src/App.jsx` — one early return

Immediately after the `if (submitted)` block (ends at line 387), before the
main `return`:

```jsx
if (form.representativeOk === null) {
  return <FilledByGate onChoose={(v) => setField('representativeOk', v)} />
}
```

Plus the import beside the other component imports (lines 4-14).

Order matters: the `submitted` check stays first. A submitted order always has
an answer, but leaving the confirmation ahead of the gate keeps the two early
returns in lifecycle order and avoids any chance of the gate shadowing a
confirmation screen.

Nothing else in `App.jsx` changes:

- `isRepFilled` and `isNewAccount` keep their current expressions. The
  `representativeOk === null` branch of `isNewAccount` becomes unreachable in
  practice; the expression is left alone rather than rewritten, because the
  data flow is unchanged and rewriting it would obscure the diff.
- The submit-time check at line 267 stays. It is now unreachable from the UI,
  but it is the client mirror of a server rule and costs one line.
- The `useEffect` at lines 95-105 still fetches seasons, reps and writers on
  mount, so those lists are already loaded when the form renders.

### 3. `frontend/src/index.css` — gate styling

Add a block **immediately after the `.brand-logo` rule** (ends line 64), i.e.
after `.order-form` (line 14). Placement matters: `.filled-by-gate` and
`.order-form` have equal specificity and the gate element carries both classes,
so the padding override only wins by coming later in the file.

```css
.filled-by-gate {
  max-width: 560px;
  text-align: center;
  padding: 3rem 2.5rem;
}
.filled-by-gate h1 {
  font-size: 1.1rem;
  font-weight: 400;
  letter-spacing: 0.06em;
  margin: 0 0 2rem;
}
.gate-choices {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.gate-choices button {
  padding: 1.1rem 1.5rem;
  background: #fff;
  color: #1d1d1b;
  border: 1px solid #d8d4cc;
  font-size: 0.95rem;
  text-transform: none;
  letter-spacing: 0.04em;
}
.gate-choices button:hover {
  border-color: #1d1d1b;
  background: #faf9f7;
}
```

**The `.gate-choices button` overrides are required, not cosmetic.** Line 647
of `index.css` styles the bare `button` element globally as a small black
uppercase pill. Without the overrides the two choices would render as compact
dark buttons rather than large targets, and "Sales Representative" would be
squeezed into an 0.8rem uppercase label.

No media query is needed. The choices are already a single column, and
`max-width: 560px` only caps the width — on a narrower viewport the block fills
what is available, with the padding staying inside that width thanks to the
global `* { box-sizing: border-box }` at `index.css:1-3`.

### 4. No backend changes

`filledBy` is still derived from the same state at `App.jsx:324`, so the
submitted payload is byte-identical. `backend/app/schemas/order.py`,
`routers/orders.py`, both PDF templates and the database are untouched. No
migration.

`/admin` and `/sign/<token>` are unaffected — the gate lives inside `App`,
which `main.jsx` only mounts for `/order_form`.

## Testing

No test runner exists in `frontend/` (`package.json` has only `dev`, `build`
and `preview`), and no backend behaviour changes, so verification is at runtime
with the `verify` skill:

1. **Gate first.** Loading `/order_form` shows the logo, the question and two
   buttons — and no part of the order form.
2. **Rep path.** Clicking "Sales Representative" reveals the form with the
   Internal Use section present and Terms/Signature absent; the submit button
   reads "Send to customer for signature".
3. **Customer path.** Reloading and clicking "Customer" reveals the form with
   Terms/Signature present, Internal Use absent, and the "Is this your first
   order?" radios in the header.
4. **Still changeable.** After choosing, the Back button returns to the gate
   without clearing entered fields (type an account name first and confirm it
   survives).
5. **Keyboard.** Tab reaches both buttons and Enter activates the focused one.

## Amendment 2026-08-05 — the header states the answer; a Back button changes it

Decision 3 above (radios stay in the header) is **superseded**. Two treatments
were built and compared from two links; the Back-button version was approved
and is now the only one. The `?v=back` switch and the radio markup are gone —
a stale `?v=back` link still works, it simply has no effect.

The header now:

- states who is filling the form in — "Filling out as **Sales
  Representative**" (or **Customer**) — rather than asking;
- carries a bordered `← BACK` button at the section's top-left that returns to
  the gate;
- puts PO # beside Order date / Collection / Ship Window on a four-column row,
  instead of on row 1 beside the old radios.

Layout notes:

- The Back button sits in **normal flow** above the logo, not absolutely
  positioned. At 375px the card is ~343px wide and the wordmark takes 260px of
  it, so a pinned control of usable size would overlap the logo.
- It carries a `:focus-visible` outline. The stylesheet's global `button` rule
  defines no focus style, so a keyboard user otherwise had no indication.
- The arrow is a separate `aria-hidden` span, so the accessible name is "Back".
- `.header-grid` is a four-column grid (`'filled filled . total'` /
  `'date season ship po'`), folding to two columns at ≤980px and to the
  existing single-column stack at ≤720px.
- PO # is rendered after Ship Window in the **DOM**, not merely placed there by
  `grid-area`, so tab order follows the visual order.
- `onBack` clears `representativeOk` to `null`, which is what drops back to the
  gate — the same condition the early return in `App.jsx` tests.
- The Back control is `type="button"`. It sits inside the order `<form>`, and a
  bare `<button>` there would submit the order.
- **Returning to the gate unmounts the form.** Everything held in `App` —
  account name, addresses, quantities, payment, notes — survives. State owned
  by the form's children does not: the "Find your Account" search box clears
  (`BuyerLookup.jsx:5-9`) and "Same as Bill To" unticks (`Addresses.jsx:59`),
  though the values it copied remain. No confirmation prompt, by decision.

## Out of scope

- Persisting the choice across reloads (`localStorage`, a cookie, or a URL
  parameter). A refresh returns to the gate, which is consistent with the rest
  of the form — no in-progress state is persisted today either.
- Any rep-specific entry URL, and any authentication of who the rep is.
- Moving the customer's "Is this your first order?" question into the gate, or
  turning the gate into a multi-step wizard.
- Changing the "Filled by" radios in the order header, or the wording of any
  existing section.
