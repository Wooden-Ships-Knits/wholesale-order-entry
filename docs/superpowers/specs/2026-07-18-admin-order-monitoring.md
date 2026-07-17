# Admin order monitoring page — design

**Status:** draft · **Date:** 2026-07-18

Admin-facing page listing submitted orders so the team can review each one,
open its PDF and tax certificate, see whether the buyer is a new account or
sits too close to an existing stockist, and accept or decline it.

## 1. Why this needs auth first

Everything on this page is sensitive:

| Item | Why it matters |
|---|---|
| Order PDF | buyer contact details, full order, card name + last 4 |
| Tax certificate | contains the buyer's tax ID |
| Order list | full customer book, one page |

Today the app has **no authentication at all**, and order PDFs/certificates are
deliberately written to `/output/orders` — outside the web root, never served by
nginx (CLAUDE.md golden rule 1). Serving them as plain links would undo that on
purpose. So auth is part of this feature, not a follow-up.

Card number and CVV are no longer rendered into the PDF (decision 2026-07-18),
which lowers the blast radius but does not remove the need to gate access.

## 2. Auth

Password + server-side session:

- One shared admin password, stored **hashed** in `.env` (`ADMIN_PASSWORD_HASH`),
  never in code. Verified with a constant-time compare.
- `POST /api/admin/login` → sets an `HttpOnly`, `Secure`, `SameSite=Strict`
  session cookie. `POST /api/admin/logout` clears it.
- A FastAPI dependency (`require_admin`) gates **every** `/api/admin/*` route,
  including the file downloads. No route opts out.
- Rate-limit login attempts; log failures without the attempted password.

Deliberately not chosen for v1: Google SSO (more setup, no per-user need yet)
and network-only restriction (no per-user trail, weakest). Revisit if the team
grows or a per-admin audit trail is required.

## 3. Table columns

| Column | Source | Notes |
|---|---|---|
| Order ID | `orders.id` (short form, 8 chars) | full uuid on hover |
| PDF file | `GET /api/admin/orders/{id}/pdf` | authenticated stream, not a static path |
| New account | `orders.account_status` / buyer-lookup result | Yes / No |
| Potential conflict | `GET /api/accounts/nearby` (see §5) | Yes / No, with distance on hover |
| Tax certificate | `GET /api/admin/orders/{id}/certificate` | `—` when `cert_filename` is null |
| Notes | `orders.notes` | truncated, full text on hover |
| Accept / decline | `POST /api/admin/orders/{id}/status` | writes `orders.status` |

## 4. File serving

Never expose `/output/orders` through nginx. Instead:

- `GET /api/admin/orders/{id}/pdf` and `.../certificate`
- Behind `require_admin`.
- Look the filename up **from the DB row**, resolve it inside
  `settings.pdf_output_dir`, and reject anything that escapes that directory
  (path traversal guard). Never build a path from user input.
- Stream with `Content-Disposition: attachment`.
- 404 when the row has no `cert_filename`.

## 5. Potential conflict

Consumes the nearby-stockist conflict check
(`docs/superpowers/specs/2026-07-17-nearby-conflict-check-design.md`,
implemented on `feat/nearby-conflict-api`): haversine KNN over account
coordinates, refined by drive time.

Depends on `bill_lat/lng` (and `ship_lat/lng`) being populated — these come from
the Google Places search on the order form and are only set when the buyer
picks a suggestion. **Orders submitted without coordinates cannot be checked**
and must show `Unknown`, not `No` — a false "No" here would silently approve a
conflicting stockist.

Open question: compute on page load (simple, slower) or store the verdict on the
order at submit time (fast, but stale if stockists change).

## 6. Accept / decline

- Uses the existing `orders.status` column (`submitted` default).
- Transitions: `submitted → accepted` / `submitted → declined`.
- Decline should capture a reason (new nullable `status_reason` column) —
  otherwise "why was this declined?" is unanswerable later.
- Record who acted and when (`status_by`, `status_at`) once auth exists.
- Needs a migration (`0003_order_status_review`).

## 7. Frontend

- Separate route/page (`/admin`), not part of the buyer form.
- Reuses the existing plain-CSS look; no new UI framework.
- Login screen when unauthenticated; table when authenticated.
- Suggested layout: `frontend/src/admin/` (`AdminApp.jsx`, `OrderTable.jsx`,
  `Login.jsx`) to keep it clearly separate from the order form components.

## 8. Open questions

1. **One shared admin password, or per-user accounts?** Shared is simpler but
   gives no audit trail — matters once accept/decline is a real decision.
2. **Is `new account` the rep's `account_status` radio, or derived from whether
   the buyer lookup matched?** They can disagree.
3. **Pagination / filtering** — how many orders before a plain list stops
   working? Filter by status (default: show `submitted` only)?
4. **Should declining notify the buyer by email**, or is it internal-only?
5. **Conflict verdict:** live vs stored at submit (see §5).
