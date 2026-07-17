# Wire New Form Fields Through Backend + Update Docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the form fields added on 2026-07-16 (notes, ship window, filled-by, payment method, lat/lng, tax-cert upload) end-to-end — schema → DB → PDF — fix the frontend payload, and bring PRD.md / architecture.md / CLAUDE.md in line with the current code.

**Architecture:** The frontend already collects these fields but the backend Pydantic schema silently drops them. We extend `OrderSubmission` (Pydantic v2, camelCase aliases), add nullable columns via Alembic migration `0002`, thread the values through the order router into the DB row and the WeasyPrint PDF context, and add the two missing payload fields (`shipWindow`, `filledBy`) plus base64 cert-file encoding in `App.jsx`. The cert file is saved beside the order PDF in `PDF_OUTPUT_DIR` (bind-mounted, never served by nginx).

**Tech Stack:** FastAPI + Pydantic v2, SQLAlchemy 2.0 + Alembic, Jinja2/WeasyPrint, React + Vite, pytest (new dev dependency).

**Constraints (CLAUDE.md golden rules):** No card number/CVV persistence — untouched. Cert upload contains tax data, not card data. All new columns nullable so migration is safe on existing rows.

---

### Task 1: Pytest infrastructure + failing schema tests

**Files:**
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/test_order_schema.py`

- [ ] **Step 1: Create `backend/requirements-dev.txt`**

```
-r requirements.txt
pytest==8.*
```

- [ ] **Step 2: Write failing tests in `backend/tests/test_order_schema.py`**

```python
"""Schema tests for POST /api/orders payload — new 2026-07-16 form fields."""
import base64

import pytest
from pydantic import ValidationError

from app.schemas.order import OrderSubmission

BASE = {
    "season": "F26",
    "shipTo": {"email": "buyer@store.com"},
}


def _sub(**extra) -> OrderSubmission:
    return OrderSubmission.model_validate({**BASE, **extra})


def test_new_top_level_fields_parse_from_camel_case():
    sub = _sub(shipWindow="08/01 - 08/31  2026", filledBy="rep", notes="Call before shipping")
    assert sub.ship_window == "08/01 - 08/31  2026"
    assert sub.filled_by == "rep"
    assert sub.notes == "Call before shipping"


def test_new_fields_default_empty_for_old_payloads():
    sub = _sub()
    assert sub.ship_window == ""
    assert sub.filled_by == ""
    assert sub.notes == ""
    assert sub.payment.method == ""
    assert sub.payment.approval_before_charge is None
    assert sub.tax_exemption.cert_file is None
    assert sub.bill_to.lat is None and sub.bill_to.lng is None


def test_address_coordinates_parse():
    sub = _sub(
        billTo={"buyerName": "A", "lat": 41.878113, "lng": -87.629799},
        shipTo={"email": "buyer@store.com", "lat": 34.052235, "lng": -118.243683},
    )
    assert sub.bill_to.lat == pytest.approx(41.878113)
    assert sub.ship_to.lng == pytest.approx(-118.243683)


def test_payment_method_parses():
    sub = _sub(payment={"method": "link"})
    assert sub.payment.method == "link"


def test_cert_file_parses_and_decodes():
    content = base64.b64encode(b"%PDF-1.4 fake").decode()
    sub = _sub(taxExemption={"certFile": {"name": "resale-cert.pdf", "contentBase64": content}})
    assert sub.tax_exemption.cert_file.decoded() == b"%PDF-1.4 fake"


def test_cert_file_rejects_disallowed_extension():
    content = base64.b64encode(b"MZ fake exe").decode()
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "evil.exe", "contentBase64": content}})


def test_cert_file_rejects_oversize():
    # > 10 MB decoded
    content = base64.b64encode(b"x" * (10 * 1024 * 1024 + 1)).decode()
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "big.pdf", "contentBase64": content}})


def test_cert_file_rejects_invalid_base64():
    with pytest.raises(ValidationError):
        _sub(taxExemption={"certFile": {"name": "cert.pdf", "contentBase64": "not@base64!!"}})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python3 -m pytest tests/test_order_schema.py -v` (in a venv with `pip install -r requirements-dev.txt`)
Expected: FAIL — `OrderSubmission` has no `ship_window`/`filled_by`/`notes`; `Payment` has no `method`; `TaxExemption` has no `cert_file`.

### Task 2: Extend the Pydantic schema

**Files:**
- Modify: `backend/app/schemas/order.py`

- [ ] **Step 1: Add fields + `CertFile` model**

In `BillTo` and `ShipTo`, append:

```python
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
```

Replace `Payment` additions (append to class):

```python
    method: str = ""                      # "link" | "card" | ""
    approval_before_charge: bool | None = None
```

Add above `TaxExemption`:

```python
# Tax-exemption certificate upload (base64 in the JSON payload).
CERT_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
CERT_MAX_BYTES = 10 * 1024 * 1024  # decoded


class CertFile(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    content_base64: str

    @field_validator("name")
    @classmethod
    def _allowed_extension(cls, v: str) -> str:
        if PurePosixPath(v.replace("\\", "/")).suffix.lower() not in CERT_ALLOWED_EXTENSIONS:
            raise ValueError("Certificate must be a PDF, JPG or PNG file.")
        return v

    @field_validator("content_base64")
    @classmethod
    def _valid_and_small_enough(cls, v: str) -> str:
        try:
            decoded = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Certificate file content is not valid base64.")
        if len(decoded) > CERT_MAX_BYTES:
            raise ValueError("Certificate file is larger than 10 MB.")
        return v

    def decoded(self) -> bytes:
        return base64.b64decode(self.content_base64, validate=True)
```

`TaxExemption` gains: `cert_file: CertFile | None = None`

`OrderSubmission` gains (after `part_ship_ok`):

```python
    ship_window: str = ""
    filled_by: str = ""    # "rep" | "customer" | ""
    notes: str = ""
```

New imports: `base64`, `binascii`, `from pathlib import PurePosixPath`, and `field_validator` from pydantic.

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Commit** — `git add backend/tests backend/requirements-dev.txt backend/app/schemas/order.py && git commit -m "feat: accept new form fields in order schema (notes, ship window, filled-by, payment method, coords, cert upload)"`

### Task 3: DB columns — migration 0002 + models

**Files:**
- Create: `backend/app/db/migrations/versions/0002_form_fields.py`
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Write migration** (style mirrors `0001_orders.py`)

```python
"""new form fields: ship window, filled-by, notes, payment method, coords, cert file

Revision ID: 0002_form_fields
Revises: 0001_orders
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_form_fields"
down_revision: Union[str, None] = "0001_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    sa.Column("ship_window", sa.Text()),
    sa.Column("filled_by", sa.Text()),            # rep | customer
    sa.Column("notes", sa.Text()),
    sa.Column("payment_method", sa.Text()),       # link | card
    sa.Column("approval_before_charge", sa.Boolean()),
    sa.Column("bill_lat", sa.Numeric(9, 6)),
    sa.Column("bill_lng", sa.Numeric(9, 6)),
    sa.Column("ship_lat", sa.Numeric(9, 6)),
    sa.Column("ship_lng", sa.Numeric(9, 6)),
    sa.Column("cert_filename", sa.Text()),        # uploaded tax-exemption cert
)


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column("orders", col)


def downgrade() -> None:
    for col in reversed(COLUMNS):
        op.drop_column("orders", col.name)
```

- [ ] **Step 2: Add matching `Order` columns in `models.py`** (all `Mapped[... | None]`, same section comments: ship_window/filled_by/notes near top, payment_method + approval_before_charge in payment block, bill_lat/bill_lng in bill-to block, ship_lat/ship_lng in ship-to block, cert_filename in tax block). Coordinates: `Mapped[Decimal | None] = mapped_column(Numeric(9, 6))`.

- [ ] **Step 3: Verify** — `python3 -c "from app.db import models"` compiles; if Docker db is running, `docker compose exec backend alembic upgrade head`; otherwise note migration runs on next deploy.

- [ ] **Step 4: Commit** — `git commit -m "feat: persist new form fields (migration 0002)"`

### Task 4: Order router + PDF save for cert

**Files:**
- Modify: `backend/app/routers/orders.py`
- Modify: `backend/app/pdf/render.py`

- [ ] **Step 1: `render.py` — generalize saving**

```python
def cert_filename(season: str, buyer_name: str, created, order_id, original_name: str) -> str:
    """WS-cert-{season}-{buyerName}-{YYYYMMDD}-{shortId}{ext} — ext from a whitelist."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", buyer_name or "unknown").strip("-")[:40] or "unknown"
    ext = Path(original_name).suffix.lower()
    return f"WS-cert-{season}-{slug}-{created:%Y%m%d}-{str(order_id)[:8]}{ext}"


def save_output_file(data: bytes, filename: str) -> str:
    out_dir = Path(settings.pdf_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(data)
    logger.info("Output file written: %s (%d bytes)", filename, len(data))
    return str(path)
```

`save_order_pdf` becomes a thin wrapper over `save_output_file`.

- [ ] **Step 2: `orders.py` — thread fields through**

In the `Order(...)` construction add:
`ship_window=payload.ship_window, filled_by=payload.filled_by, notes=payload.notes, payment_method=payload.payment.method, approval_before_charge=payload.payment.approval_before_charge, bill_lat=payload.bill_to.lat, bill_lng=payload.bill_to.lng, ship_lat=payload.ship_to.lat, ship_lng=payload.ship_to.lng, cert_filename=<computed if payload.tax_exemption.cert_file>`.

Decode cert bytes BEFORE render (`cert_bytes = payload.tax_exemption.cert_file.decoded() if ... else None`); compute `cert_filename` with the same `created_at`. After commit, save it with the same OSError handling pattern as the PDF.

PDF context additions in `"order"`: `ship_window`, `filled_by`, `notes`, `payment_method`, `approval_before_charge`, `cert_filename`.

- [ ] **Step 3: Verify** — `python3 -m pytest tests/ -v` still passes; `python3 -c "import app.routers.orders"`.

- [ ] **Step 4: Commit** — `git commit -m "feat: persist + render new form fields; save uploaded tax cert beside order PDF"`

### Task 5: PDF template

**Files:**
- Modify: `backend/app/pdf/template.html`

- [ ] **Step 1: Edits**
- Meta row: replace the "Part ship OK" cell with `Filled by` (`Sales rep` / `Customer` / `—`) and add a `Ship window` cell showing `order.ship_window or "—"`.
- Payment section: add a first row `Payment by: {{ "Payment link" if order.payment_method == "link" else "Credit card" if order.payment_method == "card" else "—" }}` and `Charge approval` (`Get approval first` / `Charge without approval` / `—`); keep card fields (blank when link). Keep the card-data warning only when method != "link".
- Tax section: add `<div class="ack">Uploaded certificate: {{ order.cert_filename or "—" }}</div>`.
- New `Notes` section (before Terms): `<div class="box">{{ order.notes or "—" }}</div>`.

- [ ] **Step 2: Verify render** — smoke-render with dummy context via a small scratch script (WeasyPrint import permitting; else Jinja render only).

- [ ] **Step 3: Commit** — `git commit -m "feat: order PDF shows ship window, filled-by, payment method, notes, cert filename"`

### Task 6: Frontend payload fixes

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Base64 helper + payload**

Add near `today()`:

```js
const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('Could not read the certificate file.'))
    reader.readAsDataURL(file)
  })
```

Make `onSubmit` build:

```js
      shipWindow: form.shipWindow,
      filledBy: form.representativeOk === true ? 'rep' : form.representativeOk === false ? 'customer' : '',
```

and, before `submitOrder`, if `certFile`: reject > 10 MB with a notice, else `taxExemption.certFile = { name: certFile.name, contentBase64: await fileToBase64(certFile) }`.

- [ ] **Step 2: Verify** — `cd frontend && npm run build` succeeds.

- [ ] **Step 3: Commit** — `git commit -m "fix: submit ship window, filled-by and tax cert upload with the order"`

### Task 7: Docs — PRD.md

**Files:**
- Modify: `docs/PRD.md`

- [ ] Update to match the 2026-07-16 form: version bump to 0.3 + date; §4 flow (lookup by email or store name; Google Maps address search; payment/tax sections only for new accounts); §5.1 (Ship Window dropdown; "Filled by" replaces "Part ship OK"; Internal Use renders only for reps); §5.2 (email / store-name / SF id); §5.3 (fax removed; Places search); §5.4 (Places search; "Same as Bill To"); §5.6 (payment-by choice, charge approval, card fields conditional; section only for new accounts); §5.7 (file upload replaces checkboxes; only for new accounts); §5.8 ("ORDER POLICIES" bullets; date field removed); §5.9 (Order written by = `Written_By__c` picklist; Rep auto = writer unless split); new §5.11 Notes; §9 open items (which seasons to sell — currently newest 2; cert file retention/serving policy; lat/lng use in Salesforce).
- [ ] Commit — `git commit -m "docs: PRD matches 2026-07-16 form changes"`

### Task 8: Docs — architecture.md

**Files:**
- Modify: `docs/architecture.md`

- [ ] Update: version bump + date; §2 stack row for Google Maps JS/Places (browser, `VITE_GOOGLE_MAPS_API_KEY`); §3.2 add `Salesperson__c` picklist (reps), `SalesTerritory__c` free text, `kugo2p__SalesOrder__c.Written_By__c` picklist; §3.3 name-lookup SOQL (`Name LIKE '%…%' ORDER BY Name LIMIT 25`) + seasons endpoint returning newest 2; §4 new orders columns (copy of migration 0002 list); §5 API table rows for `/api/reps`, `/api/territories`, `/api/order-writers`, `?name=` param; §7 PDF contents (notes, ship window, filled-by, payment method, cert filename) + cert file saved beside PDF; §9 note the browser-side Google key is referrer-restricted and no Salesforce data goes to Google (only user-typed address text).
- [ ] Commit — `git commit -m "docs: architecture matches current API surface, schema, and Google Maps integration"`

### Task 9: Docs — CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] Update: golden rule 2 nuance (Internal Use shown only when Filled by = Sales Representative — decision 2026-07-16); API surface add the three new GETs and `?name=`; env section add frontend `frontend/.env` + `VITE_GOOGLE_MAPS_API_KEY`; stack line for Google Maps Places; confirmed-mappings section add the new fields/objects; "Things to confirm" add: seasons to offer (currently newest 2, hardcoded), cert upload retention policy, admin email recipients still open.
- [ ] Commit — `git commit -m "docs: CLAUDE.md matches current code (new endpoints, Google Maps, form rules)"`

### Task 10: Final verification

- [ ] `cd backend && python3 -m pytest tests/ -v` — all pass.
- [ ] `cd frontend && npm run build` — succeeds.
- [ ] `git log --oneline` shows the task commits; working tree clean.
