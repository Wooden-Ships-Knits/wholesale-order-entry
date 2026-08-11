# CLAUDE.md — Wooden Ships Wholesale Order Form

Guidance for Claude Code (and any AI agent) working in this repo. Read `docs/PRD.md` and `docs/architecture.md` first — they are the source of truth. This file captures the rules, conventions, and constraints.

## Project in one line
A web-based wholesale order form for Wooden Ships knit sweaters: products and buyer data come live from Salesforce; submitted orders are saved to PostgreSQL, rendered to PDF, and emailed to the admin team.

## Golden rules (do not violate)
1. **Never store or log the CVV — in any form, anywhere.** No CVV column, no CVV in a PDF, an email, or a log line. It is read by nothing and kept nowhere. (Revised 2026-07-28.) The **card number** may persist only as `card_pdf_enc`: the admin-copy PDF, AES-256-GCM encrypted (`app/crypto.py`, key in `CARD_ENCRYPTION_KEY`, never in the DB), purged on Accept/Decline and by the retention sweep. It exists because Kugamon encrypts cards inside its own Visualforce page, so the monitoring team must key the number in by hand. That copy is **never written to disk, never emailed, and never logged** — it is served only by `GET /api/admin/orders/{id}/pdf?full=1`, which logs each access. No plaintext card-number column, ever. `card_last4`, `card_name` and `card_exp` may persist in the clear; the customer's PDF shows only `•••• last4`.
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
- Email: stdlib `smtplib` (SMTP, sent via FastAPI BackgroundTasks — chosen over `fastapi-mail` because the submit flow is synchronous). Order copies to the buyer (opt-in) + an admin notice on every order; both from `wholesale@wooden-ships.com`.
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
- `GET /api/accounts/nearby?lat&lng&k&maxMinutes` — new-customer conflict check (k nearest wholesale stockists; conflict = drive < 20 min default; straight-line fallback without a Google server key). Tool page = the *Conflict check* tab in `/admin` (`frontend/src/conflict/`, `/check-conflict` + `/conflict.html` 301 there); also wired into the order form as a rep-only warning modal (rep + new account + Ship To coords → dismissible popup, never blocks; stockist names hidden from customers). See docs/conflict-checker.md.
- `POST /api/conflict-email` — admin-only; drafts an **internal** email to the rep about a new store's inquiry, listing the conflicting nearby stockists by name with drive time / distance / last-order season (returns `{to, subject, body}`, sends nothing). Takes `orderId` (admin order table — store, rep, ship coords and state come from the order) or `storeName`/`repName`/`state`/`address`/`lat`/`lng` (conflict-check tab). The backend recomputes the conflicting neighbors from the coordinates. Names the stockists on purpose — the email goes to the rep, not the applicant.
- `POST /api/orders`  → validate, persist (no card#), render PDF + save uploaded tax cert, email admin
- `GET /api/reps-portal/*` — the rep dashboard at `/reps` (`frontend/src/reps/`): a rep signs in with their name + **their own** password (one hash per rep in `REPS_PASSWORD_HASHES`, roster + verification in `app/reps_auth.py` — never one shared password, or the name dropdown becomes a way into a colleague's book) and sees **only their own** orders, read-only (11 columns, no accept/decline, no emailing; the Order ID links to that order's masked buyer PDF, ownership re-checked server-side). Ownership reuses `sheets_client.rep_email_for_order` — Written By first, Sales Territory owner as the fallback — so the page and the rep's inbox always agree; an unresolvable rep sees nothing rather than everything. `_rep_row()` is a **separate serializer** from admin's `_row()` and must never emit card, conflict, certificate, Salesforce or dollar fields — `test_reps_portal.REP_ROW_KEYS` pins the exact key set. A rep session and an admin session are separate keys in the same cookie; neither passes the other's guard. See docs/superpowers/specs/2026-08-10-reps-monitoring-dashboard-design.md.
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

# Email (order copies + admin notice; blank host/user/pass = disabled)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=wholesale@wooden-ships.com
SMTP_PASS=
MAIL_FROM=wholesale@wooden-ships.com
ADMIN_EMAIL=wholesale@wooden-ships.com

# Conflict check (server-side Google key — NOT the browser key; IP-restrict it)
GOOGLE_MAPS_SERVER_API_KEY=
CONFLICT_MAX_MINUTES=20

# Rep dashboard (/reps) — ONE PASSWORD PER REP as a JSON map of normalized
# name -> hash. Never one shared password: the login is a name dropdown, so a
# shared one lets any rep open a colleague's book. Build the whole value with
#   docker compose exec backend python -m app.reps_auth "Aviva Landin=..." ...
# Blank or malformed = rep sign-in disabled (and nothing else breaks).
REPS_PASSWORD_HASHES=
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
- ~~Admin email recipient(s)~~ — confirmed 2026-07-22: `wholesale@wooden-ships.com` (reps' orders already land there; it's also the From address).
- SKU definition for the "2 pcs per SKU" rule.
- SMTP provider.
- Which seasons to sell right now — `GET /api/seasons` is hardcoded to the 2 most recent (2026-07-16).
- Uploaded tax-cert retention/access policy (files land beside the order PDFs in `output/orders`).
- Whether stored address lat/lng should sync to Salesforce.
```
