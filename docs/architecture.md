# Architecture — Wooden Ships Wholesale Order Form

**Version:** 0.1 (draft) · **Last updated:** 2026-07-13
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
- **Season / collection — CONFIRMED: encoded in the `ProductCode` prefix** (first 3 characters), e.g. `K43Y2W941` → season code `K43`. For the 2-digit number `n`: **odd → Fall, even → Spring**, and year = `floor(n/2) − 2` (as 20XX). Worked examples: `K58` → S27 (Spring 2027), `K57` → F26 (Fall 2026), `K56` → S26, `K43` → F19. *(Odd/even rule and K58→S27 given by Prada; the year formula is derived from those examples — confirm.)* Season filtering is therefore `ProductCode LIKE 'K57%'`.
- **Price:** `PricebookEntry.UnitPrice` filtered by `Pricebook2Id` (`SF_PRICEBOOK_ID`). `Pricebook2` and `PricebookEntry` are standard-shape (no custom fields) — **CONFIRMED**. `PricebookEntry` carries `ProductCode` and `Name` directly, so a single PricebookEntry query drives the whole product list. **Which price book to use for wholesale is still TBC.**
- **Sizes (X/S, S/M, M/L):** because each size is its own SKU, each size cell on the form maps to its own `Product2Id` — `order_items` stores one `sf_product_id` per size column (see §4). All Name/ProductCode parsing lives behind `map_product()` in `mapping.py`.
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

  - Other potentially relevant fields (not used in v1): `Terms__c` (payment terms picklist), `Discount_Sweaters__c` / `Discount_Accessories__c` (% discounts — **CONFIRMED: not applied on the form; discounts are handled by admin during manual processing. The form always shows price-book prices.**), `Deposit_Required__c` (%), `Season__c` (multipicklist on Account), `ContactBuying__c` (reference to buying contact).

### 3.3 Queries (SOQL, illustrative)
- Products + prices for a season, in one query on `PricebookEntry` (season = `ProductCode` prefix):
  ```sql
  SELECT Id, Product2Id, ProductCode, Name, UnitPrice
  FROM PricebookEntry
  WHERE Pricebook2Id = :bookId
    AND IsActive = true
    AND Product2.IsActive = true
    AND ProductCode LIKE 'K57%'
  ```
  The backend then parses `Name` into style/color/size and pivots per-size SKUs into the form's size columns.
- Seasons (`GET /api/seasons`): computed from the season-code formula in `mapping.py` (e.g. offer the current and upcoming season codes with labels like "F26 — Fall 2026") rather than scanned from 91k product rows. SOQL cannot group by a substring, so a config/formula-driven list is the practical option.
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
- Return all candidates so the frontend can show the "matching account" dropdown.

### 3.4 Field-mapping layer
All object/field names live in one config module (`backend/app/salesforce/mapping.py`) so renaming to match the real org is a one-file change, not a code hunt.

## 4. Data model (PostgreSQL)

```
orders
  id                 uuid pk
  season_code        text
  order_date         date
  part_ship_ok       boolean
  ship_window_note   text
  -- bill to
  buyer_name         text
  bill_street        text
  bill_city_state    text
  bill_zip           text
  tel                text
  fax                text
  -- ship to
  ship_email         text not null
  ship_street        text
  ship_city_state    text
  ship_zip           text
  resale_tax_id      text
  -- payment (NO card number / CVV stored)
  card_name          text            -- name on card only
  card_last4         text            -- optional, never full PAN
  -- tax exemption
  cert_required_ack  boolean
  cert_sending_ack   boolean
  cert_on_file       boolean
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
| GET | `/api/seasons` | List available collection/season codes |
| GET | `/api/products?season=F26` | Products + price + color for a season (from Salesforce) |
| GET | `/api/accounts?email=...` or `?accountId=...` | Buyer lookup candidates (from Salesforce) |
| POST | `/api/orders` | Validate, persist order, generate PDF, email admin |
| GET | `/api/health` | Health check |

`POST /api/orders` request includes card fields; server-side it: (1) re-validates minimums, (2) inserts order + items (no card number), (3) renders PDF including card details, (4) emails PDF to admin, (5) returns `{ orderId, status }`. Card fields are held only in memory for step 3.

## 6. Order-minimum validation (server + client)

Enforced in both places; server is authoritative.
- total pieces ≥ 18
- for each style with any qty: that style's pieces ≥ 4
- each SKU (a size within a style) with any qty: ≥ 2
- reject pre-packs (no fixed size ratios imposed)
Return a structured error listing offending styles/rows.

## 7. PDF generation

- An HTML template (Jinja2) mirroring the approved mockup is rendered to PDF via **WeasyPrint** inside the backend container. WeasyPrint's native deps (Pango, Cairo, GDK-Pixbuf) are installed in the backend image.
- PDF includes: header, bill/ship to, full line-item table with totals, payment details (for manual processing), tax-exemption acknowledgements, signature, and internal-use fields.
- Filename convention: `WS-order-{season}-{buyerName}-{YYYYMMDD}-{shortId}.pdf`.

## 8. Email delivery

- `fastapi-mail` over SMTP (provider TBD — Gmail SMTP, SendGrid, etc.).
- Env: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ADMIN_EMAIL` (comma-separated recipients).
- Body: order summary; attachment: the generated PDF.
- Buyer confirmation email is optional for v1 (the Excel form promises an email confirmation — can send a no-card summary to `ship_email`).

## 9. Security

- HTTPS/TLS terminated at Nginx; HTTP redirects to HTTPS.
- Secrets only in `.env` / VM environment; never in the repo.
- Card number + CVV: never logged, never stored, never in the DB — only transiently in memory for PDF rendering. Consider encrypting the PDF or delivering via a secure channel.
- Input validation + parameterized SQL (no string-built queries).
- Rate-limit `POST /api/orders` and the lookup endpoints.
- CORS locked to the site origin.
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
