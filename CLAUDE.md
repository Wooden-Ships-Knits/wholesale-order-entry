# CLAUDE.md — Wooden Ships Wholesale Order Form

Guidance for Claude Code (and any AI agent) working in this repo. Read `docs/PRD.md` and `docs/architecture.md` first — they are the source of truth. This file captures the rules, conventions, and constraints.

## Project in one line
A web-based wholesale order form for Wooden Ships knit sweaters: products and buyer data come live from Salesforce; submitted orders are saved to PostgreSQL, rendered to PDF, and emailed to the admin team.

## Golden rules (do not violate)
1. **Never store or log full credit card numbers or CVV.** They may only live in memory transiently to render the order PDF, then must be discarded. No card/CVV columns in the DB, ever. `card_last4` and `card_name` are the only card-related data that may persist.
2. **The web form must contain every field/section from the original Excel form** (`F26 - WS PDF Order Form.xlsx`). See PRD §5. Do not silently drop fields. The Internal Use section IS shown on the form — since 2026-07-16 only when "Filled by" = Sales Representative; Payment and Tax-exemption show only for new accounts (see PRD §5.6–5.9).
3. **All Salesforce calls happen on the backend only.** No Salesforce credentials or tokens reach the browser.
4. **Salesforce object/field names are assumptions** until confirmed. Keep them in one mapping module (`backend/app/salesforce/mapping.py`) so a rename is a one-file change.
5. **Order minimums are validated server-side** as the authority, mirrored on the client for UX. Rules: 18 pcs total, 4 per style, 2 per SKU, no pre-packs.
6. **Secrets only in `.env`** (provide `.env.example`). Never commit real credentials.

## Stack
- Runtime: **Python 3.11**.
- Frontend: React + Vite, plain CSS. Match the approved mockup (`docs/mockup`).
- Address search: Google Maps JS SDK (Places autocomplete), browser-side only; key in `frontend/.env` (`VITE_GOOGLE_MAPS_API_KEY`, referrer-restricted). See `frontend/src/lib/googleMaps.js` + `components/AddressMap.jsx`.
- Backend: **FastAPI + Uvicorn**, REST under `/api`. Pydantic v2 for models.
- Salesforce: `simple-salesforce` with username + password + security token auth (re-auth on session expiry).
- DB: PostgreSQL (own container); SQLAlchemy 2.0 + `psycopg` v3, Alembic migrations.
- PDF: WeasyPrint (Jinja2 HTML template → PDF).
- Email: `fastapi-mail` (SMTP), configurable recipients.
- **Containerized with Docker + Docker Compose** (`db`, `backend`, `nginx`). Deploy on the GCP VM via `docker compose up -d`.

## Directory conventions
```
frontend/               React app + Dockerfile + nginx.conf
backend/                Python 3.11 / FastAPI
  Dockerfile, requirements.txt, alembic.ini
  app/main.py           FastAPI app
  app/config.py         pydantic-settings
  app/routers/          seasons, products, accounts, orders
  app/salesforce/       client.py, mapping.py
  app/db/               session.py, models.py, migrations/ (alembic)
  app/pdf/              template.html (Jinja2), render.py
  app/email/            mailer.py
  app/validation/       order_minimum.py
  app/schemas/          pydantic models
docs/                   PRD.md, architecture.md, flow diagrams
docker-compose.yml
.env.example
```

## API surface (see architecture.md §5)
- `GET /api/seasons` (currently returns the 2 most recent — interim decision 2026-07-16)
- `GET /api/products?season=F26`
- `GET /api/accounts?email=...` | `?accountId=...` | `?name=...` (partial store-name match)
- `GET /api/reps` — active `Account.Salesperson__c` picklist values
- `GET /api/territories` — distinct `Account.SalesTerritory__c` values
- `GET /api/order-writers` — `kugo2p__SalesOrder__c.Written_By__c` picklist values
- `GET /api/accounts/nearby?lat&lng&k&maxMinutes` — new-customer conflict check (k nearest wholesale stockists; conflict = drive < 20 min default; straight-line fallback without a Google server key). Standalone tool page at `/conflict.html` (`frontend/src/conflict/`); also wired into the order form as a rep-only warning modal (rep + new account + Ship To coords → dismissible popup, never blocks; stockist names hidden from customers). See docs/conflict-checker.md.
- `POST /api/orders`  → validate, persist (no card#), render PDF + save uploaded tax cert, email admin
- `GET /api/health`

## Environment variables (.env.example)
```
# Server
PORT=8080
NODE_ENV=production
CORS_ORIGIN=https://order.wooden-ships.com

# Salesforce (username + password + security token auth)
SALESFORCE_USERNAME=
SALESFORCE_PASSWORD=
SALESFORCE_SECURITY_TOKEN=
SALESFORCE_DOMAIN=login          # 'login' for prod, 'test' for sandbox
# No SF_PRICEBOOK_ID: wholesale price books are resolved per season by name
# ("<season> Wholesale", e.g. "F26 Wholesale") — confirmed 2026-07-14.
# Season is encoded in ProductCode (K57 = F26: odd = Fall, even = Spring,
# year = floor(n/2) - 2 — verified against the org). See architecture.md §3.2.

# PostgreSQL
POSTGRES_USER=woodenships
POSTGRES_PASSWORD=
POSTGRES_DB=woodenships
DATABASE_URL=postgresql+psycopg://woodenships:${POSTGRES_PASSWORD}@db:5432/woodenships

# Email
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
ADMIN_EMAIL=orders@wooden-ships.com

# Conflict check (server-side Google key — NOT the browser key; IP-restrict it)
GOOGLE_MAPS_SERVER_API_KEY=
CONFLICT_MAX_MINUTES=20
```

Frontend env (`frontend/.env`, see `frontend/.env.example`):
```
VITE_GOOGLE_MAPS_API_KEY=        # browser key, referrer-restricted (Places autocomplete)
```

## Coding conventions
- Use SQLAlchemy with bound parameters — never build SQL by string concatenation.
- Validate all inbound data with Pydantic; reject bad quantities (non-negative integers).
- Keep Salesforce field names out of business logic — go through the mapping module.
- Round money for display; store `numeric` in the DB.
- Small, focused modules; keep routers thin and push logic into services.
- Log errors without leaking secrets or card data.
- Target Python 3.11; use type hints throughout.

## Build & run

Primary path is Docker Compose:
```
cp .env.example .env          # fill in secrets
docker compose build
docker compose up -d
docker compose exec backend alembic upgrade head   # migrations (if not auto-run)
```

Local dev without containers (optional):
```
# frontend
cd frontend && npm install && npm run dev

# backend
cd backend && python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

## Definition of done for v1
- All Excel fields present and functional on the web form.
- Products + prices load from Salesforce for the selected season.
- Buyer lookup auto-fills from Salesforce (with dropdown on multiple matches).
- Order minimums enforced with clear errors.
- Submit persists order + items to PostgreSQL (no card#), generates the PDF, emails admin, shows buyer confirmation.
- HTTPS, secrets in `.env`, deployable on the GCP VM.

## Things to confirm with Prada before finalizing
- ~~Salesforce objects/fields~~ — confirmed 2026-07-14: Account (person-account org, tax id = `Tax_ID_Number__c`, lookup via `ContactBuyingEmail__c`); Product2 (`Name` = STYLE-COLOR-SIZE, one record per SKU); season = `ProductCode` prefix (odd = Fall, even = Spring). Added 2026-07-16: `Account.Salesperson__c` (picklist → /api/reps), `Account.SalesTerritory__c` (free text → /api/territories), `kugo2p__SalesOrder__c.Written_By__c` (picklist → /api/order-writers). See architecture.md §3.2.
- ~~Price book~~ — confirmed 2026-07-14: per-season books named "<season> Wholesale"; no env var needed.
- ~~Season-year formula~~ — verified 2026-07-14: F26 Wholesale contains exactly the K57 products.
- ~~X/L size~~ — decision 2026-07-14: form keeps 3 size columns; X/L SKUs are not orderable on the web form.
- ~~Email lookup field~~ — confirmed: `ContactBuyingEmail__c` is the canonical lookup key.
- ~~Account discounts~~ — confirmed: form always shows price-book prices; discounts handled by admin.
- Admin email recipient(s).
- SKU definition for the "2 pcs per SKU" rule.
- SMTP provider.
- Which seasons to sell right now — `GET /api/seasons` is hardcoded to the 2 most recent (2026-07-16).
- Uploaded tax-cert retention/access policy (files land beside the order PDFs in `output/orders`).
- Whether stored address lat/lng should sync to Salesforce.
```
