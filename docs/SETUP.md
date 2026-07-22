# Setup & Run Guide — Wooden Ships Wholesale Order Form

How to run the app (API + frontend + database), how to verify each piece, and how to get into the database. Current as of Phase 4 (PDF output; email deferred).

---

## 1. Prerequisites

| Tool | Needed for | Check |
|---|---|---|
| Docker Desktop | the normal way to run everything | `docker info` |
| Python 3.11 | only for running the backend outside Docker | `python3.11 --version` |
| Node 20+ | only for running the frontend outside Docker | `node --version` |

## 2. One-time configuration: `.env`

All secrets live in `.env` at the repo root (never committed). Start from the template:

```bash
cp .env.example .env    # then fill in the blanks
```

Required values:

```
SALESFORCE_USERNAME=...
SALESFORCE_PASSWORD=...
SALESFORCE_SECURITY_TOKEN=...
SALESFORCE_DOMAIN=login        # 'login' = production org, 'test' = sandbox

POSTGRES_USER=woodenships
POSTGRES_PASSWORD=<any strong password>
POSTGRES_DB=woodenships
```

There is **no price book ID** to configure — wholesale price books are found by name (`"<season> Wholesale"`, e.g. `F26 Wholesale`).

---

## 3. Option A — Run everything with Docker Compose (recommended)

This is the production-shaped setup: three containers — `nginx` (serves the built frontend + proxies `/api`), `backend` (FastAPI), `db` (PostgreSQL 16).

> **Serving it over HTTPS on a domain?** See
> [`deploy/https-and-domain.md`](deploy/https-and-domain.md) — host-nginx + Let's
> Encrypt setup, GoDaddy DNS, CORS/Maps-key changes, and admin-over-HTTPS notes.

```bash
# start (builds images the first time)
docker compose up -d

# rebuild after changing backend or frontend code
docker compose build backend && docker compose up -d backend
docker compose build nginx   && docker compose up -d nginx

# status / logs
docker compose ps
docker compose logs -f backend

# stop everything (data survives in the pgdata volume)
docker compose down

# stop AND delete the database volume (full reset)
docker compose down -v
```

What runs where:

| Thing | URL / location |
|---|---|
| Order form (frontend) | http://localhost |
| API (through nginx) | http://localhost/api/... |
| Health check | http://localhost/api/health |
| PostgreSQL | inside the `db` container only (not exposed to the host — see §5) |
| Generated order PDFs | `./output/orders/` on the host (bind mount) |

Database migrations run automatically every time the backend container starts (`alembic upgrade head` in the container CMD). To run them by hand:

```bash
docker compose exec backend alembic upgrade head
```

Quick smoke test:

```bash
curl http://localhost/api/health                          # {"status":"ok"}
curl http://localhost/api/seasons                         # list of seasons
curl "http://localhost/api/products?season=F26"           # ~593 rows (first call takes ~8s, then cached 5 min)
curl "http://localhost/api/accounts?email=someone@x.com"  # buyer lookup
```

---

## 4. Option B — Run the pieces manually (local development)

Use this when you want hot-reload while editing code. You still need Postgres — easiest is to run **only the db container** and expose its port.

### 4.1 Database

Add a port mapping so your host can reach it — in `docker-compose.yml` under `db:` add:

```yaml
    ports:
      - "5432:5432"
```

then:

```bash
docker compose up -d db
```

(Alternatively use a locally installed PostgreSQL 16 — create the user/db to match `.env`.)

### 4.2 Backend (FastAPI)

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The backend reads `.env` from the directory it runs in (`backend/`), so link the root one there once:

```bash
ln -s ../.env .env        # from inside backend/
```

and make sure these two values are set in the root `.env` for local (non-Docker) runs:

```
DATABASE_URL=postgresql+psycopg://woodenships:<POSTGRES_PASSWORD>@localhost:5432/woodenships
PDF_OUTPUT_DIR=../output/orders
```

(Inside Docker these are overridden by docker-compose, so they don't conflict with Option A.)

Run migrations, then the server:

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

API is now at http://localhost:8080/api/health (no nginx in front).

> macOS note: WeasyPrint needs native libs for PDF rendering. If `import weasyprint` fails locally: `brew install pango cairo gdk-pixbuf libffi`. Inside Docker this is already handled.

### 4.3 Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to `http://localhost:8080` (configured in `vite.config.js`), so the backend from §4.2 must be running. Changes hot-reload instantly.

To produce the production build manually: `npm run build` (output in `frontend/dist/`).

---

## 5. Accessing the database

The `db` container is intentionally **not exposed to the host** in the default compose file (only other containers can reach it). Three ways in:

### 5.1 psql inside the container (no config changes needed)

```bash
# interactive shell
docker compose exec db psql -U woodenships -d woodenships

# one-off queries
docker compose exec db psql -U woodenships -d woodenships -c "SELECT * FROM orders ORDER BY created_at DESC LIMIT 5;"
```

### 5.2 From the host / a GUI client (TablePlus, DBeaver, pgAdmin…)

Expose the port as in §4.1 (`ports: ["5432:5432"]` on the `db` service, then `docker compose up -d db`), then connect with:

| Setting | Value |
|---|---|
| Host | localhost |
| Port | 5432 |
| Database | woodenships |
| User | woodenships |
| Password | `POSTGRES_PASSWORD` from `.env` |

> Only do this on a machine/network you trust; remove the port mapping for the GCP VM deployment.

### 5.3 Useful queries

```sql
-- recent orders (note: only card_last4 — full card numbers are never stored)
SELECT id, created_at, season_code, buyer_name, ship_email,
       total_qty, total_amount, status, card_last4
FROM orders ORDER BY created_at DESC;

-- line items for one order
SELECT style_name, color, qty_xs, qty_sm, qty_ml, line_qty, unit_price, line_total
FROM order_items WHERE order_id = '<uuid from orders.id>';

-- order count + revenue by season
SELECT season_code, count(*) AS orders, sum(total_amount) AS revenue
FROM orders GROUP BY season_code;

-- delete test orders
DELETE FROM orders WHERE buyer_name = 'Test Store';   -- items cascade automatically
```

### 5.4 Backup / restore

```bash
docker compose exec db pg_dump -U woodenships woodenships > backup-$(date +%Y%m%d).sql
docker compose exec -T db psql -U woodenships -d woodenships < backup-20260714.sql
```

---

## 6. Generated order PDFs

Every successful submission writes a PDF to `./output/orders/` (host side of the bind mount), named:

```
WS-order-{season}-{buyer}-{YYYYMMDD}-{shortOrderId}.pdf
```

The folder is git-ignored and never served by the web server. The PDF renders the payment **method** only (e.g. "Card on file") — no card number, name, or CVV ever reaches the template (see `backend/app/pdf/template.html`), so the same PDF is safely emailed to the buyer/admin.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `POSTGRES_PASSWORD must be set in .env` on `docker compose up` | add `POSTGRES_PASSWORD=...` to `.env` |
| First `/api/products` call slow (~8 s) or 504 | cold Salesforce login + 2.6k-row query; cached for 5 min afterwards. nginx timeout is already raised to 120 s |
| `/api/seasons` returns 502/error | Salesforce credentials wrong or security token expired — check `docker compose logs backend` |
| Frontend shows old UI after a change | rebuild the image (`docker compose build nginx && docker compose up -d nginx`) and hard-refresh (Cmd+Shift+R) |
| `relation "orders" does not exist` | migrations didn't run: `docker compose exec backend alembic upgrade head` |
| Port 80 already in use | stop the other server, or change the nginx mapping to `"8081:80"` in docker-compose.yml and use http://localhost:8081 |

---

## 8. Where things live (quick map)

```
.env                      secrets (never commit)
docker-compose.yml        the three services
frontend/                 React app (src/App.jsx is the form)
backend/app/
  main.py                 FastAPI app + routers
  salesforce/mapping.py   ALL Salesforce object/field names + parsers
  salesforce/client.py    SF session, queries, 5-min cache
  routers/                seasons, products, accounts, orders
  validation/order_minimum.py   the 18/4/2 rules (server authority)
  db/models.py            orders + order_items (no card columns)
  db/migrations/          Alembic
  pdf/template.html       the order PDF layout
output/orders/            generated PDFs (git-ignored, contains card data)
docs/                     PRD, architecture, this file
```
