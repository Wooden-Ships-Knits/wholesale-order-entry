# Wooden Ships — Wholesale Order Form

A web app for placing and reviewing Wooden Ships wholesale knitwear orders.
Products and buyer data come live from Salesforce; submitted orders are saved to
PostgreSQL, rendered to a PDF, and surfaced to the admin/PPIC team for review.

Two pages, one bundle:

| Path | Who | What |
|---|---|---|
| `/order_form` | buyers & sales reps | the order form |
| `/admin` | internal (PPIC) | password-gated order monitoring |

---

## Quick start

Everything runs in Docker Compose (`db`, `backend`, `nginx`).

```bash
cp .env.example .env          # then fill in the secrets — see below
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head   # apply DB migrations
```

Then open:
- **Order form** → http://localhost/order_form
- **Admin** → http://localhost/admin

### Frontend dev with hot-reload

Docker serves a *pre-built* bundle — frontend edits don't show until you rebuild
`nginx`. For fast iteration, run the Vite dev server instead (it proxies `/api`
to the running backend container):

```bash
cd frontend && npm install && npm run dev   # → http://localhost:5173
```

> **Rule of thumb:** frontend change → `docker compose up -d --build nginx`
> (or use the dev server). Backend change → `docker compose up -d --build backend`.
> The containers do **not** pick up source edits on their own.

---

## Configuration (`.env`)

See `.env.example` for the full list. The essentials:

| Variable | Purpose |
|---|---|
| `SALESFORCE_USERNAME` / `_PASSWORD` / `_SECURITY_TOKEN` | Salesforce auth (backend only) |
| `POSTGRES_USER` / `_PASSWORD` / `_DB`, `DATABASE_URL` | database |
| `CORS_ORIGIN` | the site's public origin (e.g. `https://wooden-ships.com`) |
| `SHIPPING_WINDOW_SHEET_ID` | Google Sheet of per-season ship windows |
| `GOOGLE_MAPS_SERVER_API_KEY` | **server** key for the conflict check (Geocoding + Distance Matrix); empty → straight-line fallback |
| `ADMIN_PASSWORD_HASH` | hashed admin password (see [Admin](#admin-monitoring-page)) |
| `SESSION_SECRET` | signs the admin session cookie |
| `SESSION_COOKIE_SECURE` | `true` in production (https); `false` for local http |

Frontend (`frontend/.env`):

| Variable | Purpose |
|---|---|
| `VITE_GOOGLE_MAPS_API_KEY` | **browser** key, referrer-restricted (Places autocomplete) |

Secrets live only in `.env` / `frontend/.env` and the git-ignored
`backend/credentials/` (Google service-account JSON). Never commit real values.

> ⚠️ Docker Compose interpolates `$` in `.env` values. Any secret containing `$`
> must avoid it — `ADMIN_PASSWORD_HASH` is base64-encoded for exactly this reason.

---

## Golden rules

1. **Never store, log, or render full card numbers or CVV.** They live in memory
   only during the submit request, then are discarded. Only `card_last4` and
   `card_name` persist. The PDF shows the payment method and last-4 — never the
   full number.
2. The web form must contain every field/section from the original Excel form.
3. All Salesforce calls happen backend-side; no SF credentials reach the browser.
4. Salesforce object/field names live in one module
   (`backend/app/salesforce/mapping.py`) — a rename is a one-file change.
5. Order minimums are enforced server-side (18 pcs total, 4 per style, 2 per SKU).

See `CLAUDE.md` for the full working agreement.

---

## Architecture

```
Browser ── nginx ──┬── static bundle (/order_form, /admin)
                   └── /api/* ──► FastAPI ──┬── PostgreSQL
                                            ├── Salesforce (simple-salesforce)
                                            ├── Google Sheets (ship windows)
                                            ├── Google Maps (conflict check)
                                            └── WeasyPrint (order PDF)
```

- **Frontend** — React + Vite, plain CSS. `frontend/src/App.jsx` is the order
  form; `frontend/src/admin/` is the monitoring page. Routing is path-based in
  `main.jsx` (no router dependency).
- **Backend** — FastAPI, Pydantic v2, SQLAlchemy 2.0 + `psycopg` v3, Alembic.
- **PDF** — WeasyPrint renders `backend/app/pdf/template.html`.

Deep detail: **`docs/architecture.md`**. Product/requirements: **`docs/PRD.md`**.
Environment & deploy: **`docs/SETUP.md`**.

### Project layout

```
frontend/src/
  App.jsx                order form (orchestrator)
  components/            OrderHeader, Addresses, AddressMap, BuyerLookup,
                         ProductLines, Payment, TaxExemption, TermsSignature,
                         InternalUse, Notes, ConflictWarning, Footer
  admin/                 AdminApp, Login, OrderTable, api.js  (the /admin page)
backend/app/
  main.py                FastAPI app + middleware + router wiring
  config.py              settings (pydantic-settings)
  routers/               seasons, ship_windows, products, accounts, reps,
                         orders, admin, health
  salesforce/            client.py, mapping.py  (all SF field names here)
  sheets/                client.py  (ship windows from Google Sheets)
  geo/                   distance, drive_time, conflict  (nearby-stockist check)
  admin/                 security.py  (password hashing + route guard)
  pdf/                   template.html, render.py
  db/                    models.py, session.py, migrations/ (alembic)
  schemas/               pydantic request/response models
```

---

## API surface

All under `/api`. Public endpoints feed the order form; `/api/admin/*` require a
signed-in session.

| Method | Route | Purpose |
|---|---|---|
| GET | `/seasons` | Season codes (currently the 2 most recent) |
| GET | `/ship-windows?season=F26` | Per-season ship windows (Google Sheet) |
| GET | `/products?season=F26` | Products + prices for a season (Salesforce) |
| GET | `/accounts?email=…` / `?name=…` / `?accountId=…` | Buyer lookup (name = partial store-name match) |
| GET | `/reps` | Active sales reps (`Salesperson__c` picklist) |
| GET | `/territories` | Distinct `SalesTerritory__c` values |
| GET | `/order-writers` | `Written_By__c` picklist (Internal Use dropdowns) |
| GET | `/accounts/nearby?lat&lng` | Nearby-stockist conflict check |
| POST | `/orders` | Validate, persist, render PDF, save cert |
| GET | `/health` | Health check |
| POST | `/admin/login` · `/admin/logout` · GET `/admin/session` | Admin auth |
| GET | `/admin/orders` | Order list for the monitoring table |
| POST | `/admin/orders/{id}/status` | Accept / decline |
| GET | `/admin/orders/{id}/pdf` · `/certificate` | Stream the order PDF / tax cert |

---

## Order form flow

1. **Collection** → ship windows load for that season (Google Sheet).
2. **Filled by:** Sales Representative or Customer.
   - **Customer** → *"Is this your first order?"* Yes shows Payment + Tax
     Certificate; No hides them.
   - **Sales Representative** → the Internal Use section (New/Existing account,
     rep, order-written-by, split, etc.).
3. Buyer lookup autofills from Salesforce; addresses support Google Places
   search (captures lat/lng).
4. Products, quantities (minimums enforced), payment, terms, notes → **Submit**.
5. On submit the backend persists the order, renders the PDF, saves any uploaded
   tax certificate, and — for **new accounts with coordinates** — runs the
   stockist conflict check in the background.

**New account** = the customer's "first order = Yes" *or* the rep's "New
account" radio. This drives whether Payment/Tax show, and whether the conflict
check runs.

---

## Nearby-stockist conflict check

When a **new** account's store location is within a **20-minute drive** of an
existing wholesale stockist, the system flags a possible conflict (brand
protection). Two independent surfaces consume it:

- **Live popup** (`ConflictWarning`) — warns a **rep** in the form as they set a
  new account's Ship To location. Informational; never blocks submit.
- **Admin column** — a background check after submit stores a boolean on the
  order so PPIC sees "Potential conflict: Yes/No" in the monitoring table.

Both need the store's coordinates (from the form's Google Places search). Without
a `GOOGLE_MAPS_SERVER_API_KEY`, the check degrades to straight-line distance
(≈ 10 miles) instead of real drive time. See **`docs/conflict-checker.md`**.

---

## Admin monitoring page

`/admin` — password-gated. Columns: Order ID, PDF (opens in-tab), New account,
Potential conflict, Tax certificate, Notes, Accept/Decline. Files are streamed
through authenticated endpoints (never served statically, since they carry buyer
and tax data).

**Set the admin password:**

```bash
docker compose exec backend python -m app.admin.security "your-password"
# paste the output into ADMIN_PASSWORD_HASH in .env
docker compose up -d backend
```

The password is stored only as a PBKDF2 hash — it cannot be recovered, only
reset. Design notes: `docs/superpowers/specs/2026-07-18-admin-order-monitoring.md`.

---

## Database migrations

```bash
docker compose exec backend alembic upgrade head          # apply
docker compose exec backend alembic revision -m "…"       # new (hand-written)
```

> After pulling code with a new migration, the backend **image** must be rebuilt
> (`docker compose up -d --build backend`) before `alembic upgrade` can see it —
> migrations are baked into the image, not mounted.

---

## Docs index

| File | What |
|---|---|
| `CLAUDE.md` | working agreement / conventions (source of truth) |
| `docs/PRD.md` | product requirements, every form field |
| `docs/architecture.md` | system design, data model, SF mapping, API |
| `docs/SETUP.md` | environment & deployment |
| `docs/conflict-checker.md` | nearby-stockist conflict check |
| `docs/superpowers/specs/` | design specs (conflict check, admin page) |
| `docs/*.drawio` / `*.png` | order-flow diagrams |
