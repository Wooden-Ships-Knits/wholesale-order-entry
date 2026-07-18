# Architecture — Wooden Ships Wholesale Order Form

**Version:** 0.3 · **Last updated:** 2026-07-17 *(0.3: new reps/territories/order-writers endpoints, store-name lookup, Google Maps Places on the frontend, new order columns for the 2026-07-16 form fields)*
Companion to `PRD.md`. This document describes the technical design.

---

## 1. High-level architecture

```
Buyer browser
     │  HTTPS
     ▼
┌──────────────── GCP VM · Docker Compose ─────────────────────┐
│  [nginx container]  reverse proxy, TLS                        │
│     ├── serves React SPA (static build)                       │
│     └── proxies /api/* → backend container                    │
│                                   │                           │
│  [backend container]  FastAPI (Python 3.11)                   │
│        ├── WeasyPrint (PDF)   ├── fastapi-mail (SMTP)         │
│        │                                                      │
│  [db container]  PostgreSQL (named volume)                    │
└───────────────────────────────────┼──────────────────────────┘
                                     │ HTTPS (simple-salesforce)
                                     ▼
                               Salesforce API
                    (Product2, PricebookEntry, Account, Contact)
```

Single-VM deployment via Docker Compose: `nginx`, `backend`, and `db` run as containers on the existing GCP VM. Salesforce and the SMTP provider are external.

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | **Python 3.11** | backend language/runtime |
| Frontend | React + Vite | SPA; served as a static build by Nginx |
| Styling | Plain CSS / CSS modules | Match the approved mockup |
| Backend | **FastAPI + Uvicorn** | REST API under `/api` |
| Validation | Pydantic v2 | request/response models |
| Salesforce client | `simple-salesforce` | OAuth2, product + account queries |
| Database | PostgreSQL | orders + order_items (its own container) |
| DB access | SQLAlchemy 2.0 + `psycopg` (v3); Alembic migrations | typed queries + versioned schema |
| PDF | WeasyPrint (HTML template → PDF) | high visual fidelity; pure-Python, container-friendly |
| Email | `fastapi-mail` (SMTP) | configurable recipients |
| Config | `.env` (pydantic-settings) | secrets never committed |
| Address search | **Google Maps JS SDK (Places autocomplete)** | browser-side only; key in `frontend/.env` as `VITE_GOOGLE_MAPS_API_KEY` (referrer-restricted) |
| Containerization | **Docker + Docker Compose** | one container per service |

> Everything runs in containers via Docker Compose (see §10). Frontend is still React/JS — only the backend is Python.

## 3. Salesforce integration

### 3.1 Auth
- **Username + password + security token** via `simple-salesforce` — this is the method already in use. Store in `.env`:
  `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`, and `SALESFORCE_DOMAIN` (`login` for production, `test` for a sandbox).
- Client init:
  `Salesforce(username=..., password=..., security_token=..., domain=os.getenv("SALESFORCE_DOMAIN","login"))`.
- The session is created at startup and reused; on session-expiry errors the client re-authenticates automatically.
- All Salesforce calls go through the backend only — the browser never sees Salesforce credentials.

### 3.2 Objects & fields (defaults — CONFIRM against the real org)
- **Products:** `Product2` — **object/fields CONFIRMED 2026-07-14** (~91.7k records in the org). Relevant fields: `Id`, `Name`, `ProductCode`, `IsActive`, `Family`, `Style__c` (style grouping), `SKU__c`, `UPCBarcode__c`. There is **no dedicated color/size/season field** — everything is encoded in `Name` and `ProductCode`:
  - **`Name` = `STYLE-COLOR-SIZE`**, e.g. `SKI PULLOVER-NIGHT/BONFIRE-X/S` → style `SKI PULLOVER`, color `NIGHT/BONFIRE`, size `X/S`. Parse **from the right**: last `-` segment = size (`X/S` | `S/M` | `M/L`), second-to-last = color (may itself contain `/`), remainder = style name.
  - **One `Product2` record per SKU** (style × color × size). The backend groups records by style + color and pivots the three sizes into the form's size columns.
- **Season / collection — CONFIRMED & VERIFIED (2026-07-14):** encoded in `ProductCode` as leading letters + a 2-digit number (`K57A5W191` → 57; prefixes vary: `K` knits, `A` accessories, `PK` pillow covers). For the number `n`: **odd → Fall, even → Spring**, year = `floor(n/2) − 2` (as 20XX) — so `K57` = F26, `K58` = S27, `K43` = F19. **Verified against the org: the "F26 Wholesale" price book contains exactly and only K57 products (2,640 entries).**
- **Price / price book — CONFIRMED (2026-07-14): one wholesale price book per season, named `"<season> Wholesale"`** (e.g. `F26 Wholesale`; `S27`, `S26`, `F25` books all exist and are active). The season selector maps directly to a book by name — **no `SF_PRICEBOOK_ID` env var**; the naming pattern lives in `mapping.py`. `Pricebook2`/`PricebookEntry` are standard-shape; `PricebookEntry` carries `ProductCode` and `Name` directly, so a single query drives the whole product list. Season prefix filtering is unnecessary (each book already contains only its season) but the formula is kept in `mapping.py` for validation/labels.
- **Sizes — DECISION (2026-07-14): the form has exactly 3 size columns (X/S, S/M, M/L).** The org also carries `X/L` SKUs (548 of 593 F26 style+colors) and `O/S` accessories; these are **not orderable on the web form** and are skipped (counted in mapping stats) when grouping. Each size cell maps to its own `Product2Id` — `order_items` stores one `sf_product_id` per size column (see §4). All Name/ProductCode parsing lives behind `mapping.py` (`parse_product_name`, `group_products`).
- **Buyer:** `Account` — **CONFIRMED 2026-07-14** against the real org. This is a **Person Account-enabled org**, so buyer email/person data lives directly on `Account` (no `Contact` join). Lookup by email or `Account.Id`.
  - **Email lookup key — CONFIRMED:** `ContactBuyingEmail__c` (the buying contact's email) is the canonical lookup field. (`PersonEmail` and `Email__c` also exist but are not used for lookup.)
  - **Confirmed form-autofill mapping:**

    | Form field | Account field |
    |---|---|
    | Buyer name | `Name` |
    | Bill To street | `BillingStreet` |
    | Bill To city/state | `BillingCity`, `BillingState` |
    | Bill To zip | `BillingPostalCode` |
    | Tel | `Phone` (secondary: `Phone2__c`) |
    | Fax | `Fax` |
    | Ship To street | `ShippingStreet` |
    | Ship To city/state | `ShippingCity`, `ShippingState` |
    | Ship To zip | `ShippingPostalCode` |
    | Ship To email | `ContactBuyingEmail__c` |
    | Resale tax ID | `Tax_ID_Number__c` |
    | Internal Use: Rep | `Salesperson__c` (picklist); also `Internal_Rep__c` (reference) |
    | Internal Use: certificate on file | derive from `Tax_ID_Verified__c` (+ `Tax_ID_Expires__c` not past) |

  - **Picklists / option sources (added 2026-07-16):**
    - `Account.Salesperson__c` — picklist; active values feed `GET /api/reps`.
    - `Account.SalesTerritory__c` — free text ("Midwest - Aviva Landin", …); the option list for `GET /api/territories` is the distinct values in use (`GROUP BY`), not a picklist describe.
    - `kugo2p__SalesOrder__c.Written_By__c` — picklist on the managed-package sales order object; active values feed `GET /api/order-writers` and the Internal Use "Order written by" / "Split with" dropdowns.
  - Other potentially relevant fields (not used in v1): `Terms__c` (payment terms picklist), `Discount_Sweaters__c` / `Discount_Accessories__c` (% discounts — **CONFIRMED: not applied on the form; discounts are handled by admin during manual processing. The form always shows price-book prices.**), `Deposit_Required__c` (%), `Season__c` (multipicklist on Account), `ContactBuying__c` (reference to buying contact).

### 3.3 Queries (SOQL, illustrative)
- Seasons (`GET /api/seasons`) — the active per-season wholesale books:
  `SELECT Id, Name FROM Pricebook2 WHERE IsActive = true AND Name LIKE '% Wholesale'`
  → parse the season code off each name, label via the formula ("F26 — Fall 2026"), sort newest first.
- Products + prices for a season, in one query on the season's book:
  ```sql
  SELECT Product2Id, ProductCode, UnitPrice, Product2.Name
  FROM PricebookEntry
  WHERE Pricebook2Id = :bookId
    AND IsActive = true
    AND Product2.IsActive = true
  ```
  The backend parses `Product2.Name` into style/color/size, skips non-form sizes (X/L, O/S), and pivots per-size SKUs into the form's three size columns. Responses are cached in-memory for 5 minutes.
- Account lookup by email (person-account org — query `Account` directly, no `Contact` join):
  ```sql
  SELECT Id, Name, IsPersonAccount,
         BillingStreet, BillingCity, BillingState, BillingPostalCode,
         ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode,
         Phone, Fax, ContactBuyingEmail__c,
         Tax_ID_Number__c, Tax_ID_Verified__c, Tax_ID_Expires__c, Salesperson__c
  FROM Account
  WHERE ContactBuyingEmail__c = :email
  ```
  Lookup by account ID uses the same SELECT with `WHERE Id = :accountId`.
- **Lookup by store name (added 2026-07-16):** same SELECT with
  `WHERE Name LIKE '%:name%' ORDER BY Name LIMIT 25` — partial, case-insensitive; `%`/`_` in user input are escaped; capped so a broad term cannot pull the whole org. The frontend routes a query containing `@` to email, a bare 15/18-char id to accountId, anything else to name.
- Return all candidates so the frontend can show the "matching account" dropdown.
- `GET /api/seasons` currently returns only the **two most recent** wholesale books (interim decision 2026-07-16 — confirm which seasons should be on sale).

### 3.4 Field-mapping layer
All object/field names live in one config module (`backend/app/salesforce/mapping.py`) so renaming to match the real org is a one-file change, not a code hunt.

## 4. Data model (PostgreSQL)

```
orders
  id                 uuid pk
  season_code        text
  order_date         date
  part_ship_ok       boolean         -- legacy; UI field replaced by filled_by 2026-07-16
  ship_window_note   text
  ship_window        text            -- buyer-selected calendar-month window
  filled_by          text            -- rep | customer
  notes              text            -- free-text Notes section
  -- bill to
  buyer_name         text
  bill_street        text
  bill_city_state    text
  bill_zip           text
  tel                text
  fax                text
  bill_lat           numeric(9,6)    -- from Google Places search (optional)
  bill_lng           numeric(9,6)
  -- ship to
  ship_email         text not null
  ship_street        text
  ship_city_state    text
  ship_zip           text
  resale_tax_id      text
  ship_lat           numeric(9,6)
  ship_lng           numeric(9,6)
  -- payment (NO card number / CVV stored)
  payment_method     text            -- link | card
  approval_before_charge boolean     -- card only
  card_name          text            -- name on card only
  card_last4         text            -- optional, never full PAN
  -- tax exemption
  cert_required_ack  boolean
  cert_sending_ack   boolean
  cert_on_file       boolean
  cert_filename      text            -- uploaded cert, saved beside the order PDF
  -- signature / terms
  signature_name     text
  signature_date     date
  terms_accepted     boolean
  -- internal use
  new_or_reorder     text
  account_status     text            -- new / existing
  campaign           text
  po_number          text
  rep                text
  order_written_by   text
  split_with         text
  -- salesforce link
  sf_account_id      text
  -- totals
  total_qty          integer
  total_amount       numeric(12,2)
  status             text            -- submitted / processed
  created_at         timestamptz default now()

order_items
  id                 uuid pk
  order_id           uuid fk -> orders.id
  -- one Product2 per SKU (style×color×size), so each size cell has its own id
  sf_product_id_xs   text
  sf_product_id_sm   text
  sf_product_id_ml   text
  code               text            -- style-level code (ProductCode without size suffix)
  style_name         text
  color              text
  qty_xs             integer default 0
  qty_sm             integer default 0
  qty_ml             integer default 0
  line_qty           integer
  unit_price         numeric(10,2)
  line_total         numeric(12,2)
```

**Card number and CVV are never columns.** They exist only in the request payload long enough to render the PDF, then are dropped.

## 5. API endpoints (FastAPI, under `/api`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/seasons` | Collection/season codes (currently the 2 most recent) |
| GET | `/api/products?season=F26` | Products + price + color for a season (from Salesforce) |
| GET | `/api/accounts?email=...` / `?accountId=...` / `?name=...` | Buyer lookup candidates (from Salesforce; `name` = partial store-name match) |
| GET | `/api/ship-windows?season=F26` | Per-season ship windows from the planning Google Sheet |
| GET | `/api/reps` | Active sales reps (`Account.Salesperson__c` picklist) |
| GET | `/api/territories` | Distinct `Account.SalesTerritory__c` values in use |
| GET | `/api/order-writers` | `Written_By__c` picklist (Internal Use dropdowns) |
| GET | `/api/accounts/nearby?lat=..&lng=..&k=5&maxMinutes=20` | New-customer conflict check: k nearest wholesale stockists + drive-time verdict |
| POST | `/api/orders` | Validate, persist order, generate PDF (+ save uploaded tax cert), email admin *(email deferred)* |
| GET | `/api/health` | Health check |
| POST | `/api/admin/login` · `/api/admin/logout` · GET `/api/admin/session` | Admin auth (shared password → signed session cookie) |
| GET | `/api/admin/orders` | Order list for the monitoring page (auth) |
| POST | `/api/admin/orders/{id}/status` | Accept / decline an order (auth) |
| GET | `/api/admin/orders/{id}/pdf` · `/certificate` | Stream the order PDF / tax cert inline (auth) |

The `/api/accounts/nearby` verdict is consumed two ways: a live `ConflictWarning` popup for reps in the order form, and a background check on `POST /api/orders` that stores `orders.has_conflict` for the admin monitoring page. `/api/admin/*` routes are gated by a session cookie (see `docs/superpowers/specs/2026-07-18-admin-order-monitoring.md`); files are streamed through the app, never served statically.

**`GET /api/accounts/nearby`** (added 2026-07-17, spec: `docs/superpowers/specs/2026-07-17-nearby-conflict-check-design.md`): flags a new customer whose Ship To point is within a **20-minute drive** (default; `maxMinutes` overridable, env default `CONFLICT_MAX_MINUTES`) of an existing `Type='Wholesale'` account. Flow: cached Salesforce query of geocoded wholesale accounts (`ShippingLatitude/Longitude`, Salesforce-populated) → pure-Python haversine KNN pre-filter (≤ 25 candidates) → one Google Distance Matrix call (server key `GOOGLE_MAPS_SERVER_API_KEY`) → `{conflict, mode, maxMinutes, neighbors[{accountId, name, cityState, distanceMiles, driveMinutes}]}`. If the key is unset or Google fails, the endpoint degrades to `mode: "straight-line"` (conflict at `maxMinutes × 0.5` miles ≈ 30 mph) instead of erroring. Modules: `app/geo/{distance,drive_time,conflict}.py`.

`POST /api/orders` request includes card fields; server-side it: (1) re-validates minimums, (2) inserts order + items (no card number — only `card_name` + `card_last4`), (3) renders the PDF (payment **method** and last-4 only; **never** the full number or CVV), (4) saves any uploaded tax certificate beside the PDF, (5) for a new account with coordinates, schedules the background conflict check, (6) returns `{ orderId, status }`. The full card number and CVV are read once (to derive last-4) and discarded with the request; admin email is deferred. **Update 2026-07-18: the PDF no longer renders the full card number/CVV** — collect-to-charge is being reworked toward the payment-link flow.

## 6. Order-minimum validation (server + client)

Enforced in both places; server is authoritative.
- total pieces ≥ 18
- for each style with any qty: that style's pieces ≥ 4
- each SKU (a size within a style) with any qty: ≥ 2
- reject pre-packs (no fixed size ratios imposed)
Return a structured error listing offending styles/rows.

## 7. PDF generation

- An HTML template (Jinja2) mirroring the approved mockup is rendered to PDF via **WeasyPrint** inside the backend container. WeasyPrint's native deps (Pango, Cairo, GDK-Pixbuf) are installed in the backend image.
- PDF includes: header (incl. filled-by and buyer-selected ship window), bill/ship to, full line-item table with totals, payment method + details (card fields only when paying by card), tax-exemption acknowledgements + uploaded-cert filename, notes, signature, and internal-use fields.
- Filename convention: `WS-order-{season}-{buyerName}-{YYYYMMDD}-{shortId}.pdf`.
- An uploaded tax-exemption certificate (PDF/JPG/PNG ≤ 10 MB, base64 in the submit payload) is written to the same output directory as `WS-cert-{season}-{buyerName}-{YYYYMMDD}-{shortId}.{ext}` and referenced from `orders.cert_filename`.

## 8. Email delivery — DEFERRED (2026-07-14)

**v1 stops at PDF output**: the generated PDF is written to a persistent output directory (bind-mounted volume) on the server for admin retrieval; no email is sent. The design below is kept for the follow-up phase:

- `fastapi-mail` over SMTP (provider TBD — Gmail SMTP, SendGrid, etc.).
- Env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ADMIN_EMAIL` (comma-separated recipients).
- Body: order summary; attachment: the generated PDF.
- Buyer confirmation email is optional (the Excel form promises an email confirmation — can send a no-card summary to `ship_email`).

## 9. Security

- HTTPS/TLS terminated at Nginx; HTTP redirects to HTTPS.
- Secrets only in `.env` / VM environment; never in the repo.
- Card number + CVV: never logged, never stored, never in the DB — only transiently in memory for PDF rendering. Consider encrypting the PDF or delivering via a secure channel.
- Input validation + parameterized SQL (no string-built queries).
- Rate-limit `POST /api/orders` and the lookup endpoints.
- CORS locked to the site origin.
- Google Maps: the browser key (`VITE_GOOGLE_MAPS_API_KEY`) is public by design — restrict it by HTTP referrer and to the Maps JavaScript + Places APIs in the Google Cloud console. Only user-typed address text goes to Google; no Salesforce or order data does.
- Google Maps server key (`GOOGLE_MAPS_SERVER_API_KEY`, conflict check): separate key, IP-restricted to the VM, Distance Matrix API only. The conflict check sends Google **raw coordinates only** — never account names or Salesforce ids.
- Uploaded tax certs: type whitelist (PDF/JPG/PNG), 10 MB cap, stored filename is server-generated (user filename discarded except its extension); stored outside the web root, never served by nginx.
- Future: migrate card capture to Stripe Elements to eliminate PCI scope.

## 10. Deployment — Docker (GCP VM)

Everything ships as containers orchestrated by Docker Compose on the VM.

Services:
- `db` — `postgres:16`, data on a named volume, not exposed publicly.
- `backend` — FastAPI image (`python:3.11-slim` base + WeasyPrint system libs), runs Uvicorn; Alembic migrations run on start.
- `nginx` — serves the built React SPA and reverse-proxies `/api` to `backend`; terminates TLS.

```
# on the GCP VM
cp .env.example .env        # fill in secrets
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head   # if not auto-run
```

Example `docker-compose.yml` shape:
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: woodenships
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
  backend:
    build: ./backend
    env_file: .env
    depends_on: [db]
  nginx:
    build: ./frontend
    ports: ["80:80", "443:443"]
    depends_on: [backend]
volumes:
  pgdata:
```

Backend Dockerfile notes: base `python:3.11-slim`; `apt-get install` WeasyPrint deps (`libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev libcairo2`); `pip install -r requirements.txt`; run `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

- `.env` lives on the VM (not committed). Provision Salesforce + SMTP + DB credentials there.
- Basic logging + a `/api/health` endpoint for uptime checks.

## 11. Repo structure (proposed)

```
/frontend             React + Vite app (mirrors the approved mockup)
  Dockerfile          build SPA + nginx serve + reverse proxy
  nginx.conf
/backend              Python 3.11 / FastAPI
  Dockerfile
  requirements.txt
  alembic.ini
  /app
    main.py           FastAPI app + router registration
    config.py         pydantic-settings
    /routers          seasons, products, accounts, orders
    /salesforce       client.py, mapping.py
    /db               session.py, models.py, /migrations (alembic)
    /pdf              template.html (Jinja2), render.py
    /email            mailer.py
    /validation       order_minimum.py
    /schemas          pydantic models
/docs                 PRD.md, architecture.md, flow diagrams
docker-compose.yml
.env.example
```
