# Order-copy Email + Admin Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a buyer opts in on the order form, email them a copy of their order PDF; and email an admin notification to `wholesale@wooden-ships.com` on every order.

**Architecture:** Add SMTP settings to config; a stdlib-`smtplib` transport module (`mailer.py`) and a content/orchestration module (`order_email.py`); accept the two new `Terms` fields in the schema; schedule both sends as FastAPI `BackgroundTasks` after the order commits so mail never blocks or fails an order. The attached PDF is the existing card-free order PDF.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2 (`EmailStr`), stdlib `smtplib`/`email.message`, pytest with `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-07-22-order-copy-email-design.md`

**Running tests:** from the repo root, `cd backend && python -m pytest <path> -v` (or `docker compose exec backend python -m pytest <path> -v` if you run inside the container). No new dependencies — `smtplib` is stdlib and `email-validator` (for `EmailStr`) is already in `backend/requirements.txt`.

## File Structure

- **Modify** `backend/app/schemas/order.py` — add `order_copy` / `order_copy_email` to `Terms` + a model validator.
- **Modify** `backend/app/config.py` — SMTP settings + `mail_configured` / `mail_sender` helpers.
- **Create** `backend/app/email/mailer.py` — SMTP transport only.
- **Create** `backend/app/email/order_email.py` — email content + scheduling orchestration.
- **Modify** `backend/app/routers/orders.py` — build the email context and schedule the sends after commit.
- **Modify** `backend/tests/test_order_schema.py`, **create** `backend/tests/test_mailer.py`, `backend/tests/test_order_email.py`, `backend/tests/test_config_mail.py`.
- **Modify** `.env.example`, `CLAUDE.md`, `docs/SETUP.md`.

---

### Task 1: Schema — accept the opt-in fields

**Files:**
- Modify: `backend/app/schemas/order.py` (import line 12; `Terms` class lines 91-94)
- Test: `backend/tests/test_order_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_order_schema.py`:

```python
def test_order_copy_defaults_off_for_old_payloads():
    sub = _sub()
    assert sub.terms.order_copy is False
    assert sub.terms.order_copy_email is None


def test_order_copy_with_email_parses_from_camel_case():
    sub = _sub(terms={"orderCopy": True, "orderCopyEmail": "cust@store.com"})
    assert sub.terms.order_copy is True
    assert sub.terms.order_copy_email == "cust@store.com"


def test_order_copy_true_requires_an_email():
    with pytest.raises(ValidationError):
        _sub(terms={"orderCopy": True})


def test_order_copy_true_rejects_invalid_email():
    with pytest.raises(ValidationError):
        _sub(terms={"orderCopy": True, "orderCopyEmail": "not-an-email"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_order_schema.py -v -k order_copy`
Expected: FAIL — `order_copy` attribute does not exist / validator not present.

- [ ] **Step 3: Implement the schema change**

In `backend/app/schemas/order.py`, add `model_validator` to the pydantic import on line 12:

```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator
```

Replace the `Terms` class (lines 91-94):

```python
class Terms(CamelModel):
    signature_name: str = ""
    signature_date: date | None = None
    accepted: bool = False
    order_copy: bool = False
    order_copy_email: EmailStr | None = None

    @model_validator(mode="after")
    def _require_copy_email(self) -> "Terms":
        if self.order_copy and not self.order_copy_email:
            raise ValueError("order_copy_email is required when order_copy is set")
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_order_schema.py -v`
Expected: PASS (all, including the pre-existing tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/order.py backend/tests/test_order_schema.py
git commit -m "feat: accept order-copy opt-in fields on Terms schema"
```

---

### Task 2: Config — SMTP settings + helpers

**Files:**
- Modify: `backend/app/config.py` (add fields after the admin/session block, before class end)
- Test: `backend/tests/test_config_mail.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config_mail.py`:

```python
"""SMTP config helpers on Settings."""
from app.config import settings


def test_mail_configured_true_when_host_user_pass_set(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "smtp_pass", "app-password")
    assert settings.mail_configured is True


def test_mail_configured_false_when_any_missing(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "smtp_pass", "")
    assert settings.mail_configured is False


def test_mail_sender_falls_back_to_smtp_user(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(settings, "mail_from", "")
    assert settings.mail_sender == "wholesale@wooden-ships.com"


def test_mail_sender_prefers_explicit_from(monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "login@wooden-ships.com")
    monkeypatch.setattr(settings, "mail_from", "wholesale@wooden-ships.com")
    assert settings.mail_sender == "wholesale@wooden-ships.com"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config_mail.py -v`
Expected: FAIL — `smtp_host` / `mail_configured` / `mail_sender` do not exist.

- [ ] **Step 3: Implement the config fields**

In `backend/app/config.py`, add after the `session_cookie_secure: bool = True` line (line 44), still inside the `Settings` class:

```python

    # Outbound email (order copies + admin notice). Gmail/Workspace SMTP.
    # Blank host/user/pass = mail disabled: the app logs a warning and skips
    # sending, orders still succeed. See app/email/mailer.py.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    mail_from: str = ""  # From address; falls back to smtp_user when blank
    admin_email: str = "wholesale@wooden-ships.com"

    @property
    def mail_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass)

    @property
    def mail_sender(self) -> str:
        return self.mail_from or self.smtp_user
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_config_mail.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config_mail.py
git commit -m "feat: add SMTP settings and mail helpers to config"
```

---

### Task 3: Mailer — SMTP transport

**Files:**
- Create: `backend/app/email/mailer.py`
- Test: `backend/tests/test_mailer.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_mailer.py`:

```python
"""SMTP transport: message building, send, and the unconfigured no-op."""
from unittest.mock import MagicMock, patch

from app.email import mailer


def _configure(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer.settings, "smtp_port", 587)
    monkeypatch.setattr(mailer.settings, "smtp_user", "wholesale@wooden-ships.com")
    monkeypatch.setattr(mailer.settings, "smtp_pass", "pw")
    monkeypatch.setattr(mailer.settings, "mail_from", "")


def test_send_email_builds_message_and_sends(monkeypatch):
    _configure(monkeypatch)
    fake_smtp = MagicMock()
    ctx_mgr = MagicMock()
    ctx_mgr.__enter__.return_value = fake_smtp
    with patch("app.email.mailer.smtplib.SMTP", return_value=ctx_mgr) as SMTP:
        ok = mailer.send_email(
            "cust@store.com", "Subj", "Body text",
            [("order.pdf", b"%PDF-1.4", "pdf")],
        )
    assert ok is True
    SMTP.assert_called_once_with("smtp.test", 587, timeout=10)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("wholesale@wooden-ships.com", "pw")
    sent = fake_smtp.send_message.call_args[0][0]
    assert sent["To"] == "cust@store.com"
    assert sent["From"] == "wholesale@wooden-ships.com"
    assert sent["Subject"] == "Subj"
    attachments = list(sent.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "order.pdf"


def test_send_email_skips_when_unconfigured(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_host", "")
    with patch("app.email.mailer.smtplib.SMTP") as SMTP:
        ok = mailer.send_email("cust@store.com", "S", "B")
    assert ok is False
    SMTP.assert_not_called()


def test_send_email_returns_false_on_smtp_error(monkeypatch):
    _configure(monkeypatch)
    with patch("app.email.mailer.smtplib.SMTP", side_effect=OSError("boom")):
        ok = mailer.send_email("cust@store.com", "S", "B")
    assert ok is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_mailer.py -v`
Expected: FAIL — `app.email.mailer` does not exist.

- [ ] **Step 3: Implement the mailer**

Create `backend/app/email/mailer.py`:

```python
"""SMTP transport for outbound app email (order copies + admin notice).

Pure transport — no order/business logic. Uses stdlib smtplib so it fits the
synchronous request / BackgroundTasks flow without an async dependency. Silently
no-ops (logs a warning) when SMTP isn't configured, so the app runs without mail
credentials and an order is never blocked by mail.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Send a plain-text email with optional attachments.

    attachments: list of (filename, data, mime_subtype), e.g.
    ("WS-order.pdf", b"%PDF...", "pdf"). Returns True on send, False if SMTP is
    not configured or any error occurs (both logged; never raises).
    """
    if not settings.mail_configured:
        logger.warning("Email not sent to %s: SMTP is not configured", to)
        return False

    msg = EmailMessage()
    msg["From"] = settings.mail_sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    for filename, data, subtype in attachments or []:
        msg.add_attachment(data, maintype="application", subtype=subtype, filename=filename)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
    return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_mailer.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email/mailer.py backend/tests/test_mailer.py
git commit -m "feat: add smtplib email transport module"
```

---

### Task 4: Order email — content + scheduling

**Files:**
- Create: `backend/app/email/order_email.py`
- Test: `backend/tests/test_order_email.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_order_email.py`:

```python
"""Order email content builders and background scheduling."""
from unittest.mock import MagicMock

from app.email import order_email

CTX = {
    "short_id": "abc12345",
    "season_code": "F26",
    "season_label": "Fall 2026",
    "buyer_name": "A Pied",
    "total_qty": 24,
    "total_amount": 1234.5,
}


def test_admin_email_has_key_facts_and_no_card():
    subject, body = order_email.admin_email(CTX)
    assert "F26" in subject and "A Pied" in subject and "24" in subject
    assert "Fall 2026" in body and "1,234.50" in body and "abc12345" in body
    assert "card" not in body.lower()


def test_buyer_email_is_friendly_and_no_card():
    subject, body = order_email.buyer_email(CTX)
    assert "Fall 2026" in subject
    assert "Thank you" in body and "A Pied" in body
    assert "card" not in body.lower()


def test_schedule_adds_only_admin_when_not_opted_in():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=False, order_copy_email=None,
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 1
    assert bg.add_task.call_args_list[0][0][0] is order_email.send_admin_copy


def test_schedule_adds_buyer_copy_when_opted_in():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=True, order_copy_email="cust@store.com",
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 2
    funcs = [c[0][0] for c in bg.add_task.call_args_list]
    assert order_email.send_admin_copy in funcs
    assert order_email.send_buyer_copy in funcs
    buyer_call = next(
        c for c in bg.add_task.call_args_list if c[0][0] is order_email.send_buyer_copy
    )
    assert buyer_call[0][1] == "cust@store.com"


def test_schedule_skips_buyer_when_opted_in_but_email_missing():
    bg = MagicMock()
    order_email.schedule_order_emails(
        bg, order_copy=True, order_copy_email=None,
        ctx=CTX, pdf_bytes=b"%PDF", filename="o.pdf",
    )
    assert bg.add_task.call_count == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_order_email.py -v`
Expected: FAIL — `app.email.order_email` does not exist.

- [ ] **Step 3: Implement the order-email module**

Create `backend/app/email/order_email.py`:

```python
"""Order email content + background scheduling.

Content builders return (subject, body); orchestrators attach the card-free
order PDF and delegate transport to app.email.mailer. schedule_order_emails is
the single entry point the orders router calls after commit.
"""
import logging

from app.config import settings
from app.email import mailer

logger = logging.getLogger(__name__)


def _summary(ctx: dict) -> str:
    return (
        f"Order: {ctx['short_id']}\n"
        f"Season: {ctx['season_label']} ({ctx['season_code']})\n"
        f"Buyer: {ctx['buyer_name']}\n"
        f"Total pieces: {ctx['total_qty']}\n"
        f"Total: ${ctx['total_amount']:,.2f}\n"
    )


def admin_email(ctx: dict) -> tuple[str, str]:
    subject = (
        f"New wholesale order — {ctx['buyer_name']} "
        f"({ctx['season_code']}) — {ctx['total_qty']} pcs"
    )
    body = "A new wholesale order was submitted.\n\n" + _summary(ctx) + "\nThe order form PDF is attached."
    return subject, body


def buyer_email(ctx: dict) -> tuple[str, str]:
    subject = f"Your Wooden Ships wholesale order — {ctx['season_label']}"
    body = (
        f"Thank you for your Wooden Ships wholesale order, {ctx['buyer_name']}.\n\n"
        + _summary(ctx)
        + "\nYour order copy is attached as a PDF.\n\n— Wooden Ships"
    )
    return subject, body


def send_admin_copy(ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    subject, body = admin_email(ctx)
    return mailer.send_email(settings.admin_email, subject, body, [(filename, pdf_bytes, "pdf")])


def send_buyer_copy(to: str, ctx: dict, pdf_bytes: bytes, filename: str) -> bool:
    subject, body = buyer_email(ctx)
    return mailer.send_email(to, subject, body, [(filename, pdf_bytes, "pdf")])


def schedule_order_emails(
    background,
    *,
    order_copy: bool,
    order_copy_email: str | None,
    ctx: dict,
    pdf_bytes: bytes,
    filename: str,
) -> None:
    """Queue the admin notice (always) and the buyer copy (only when opted in).

    Runs via FastAPI BackgroundTasks after the response — a slow/failed Gmail
    never blocks or fails the order.
    """
    background.add_task(send_admin_copy, ctx, pdf_bytes, filename)
    if order_copy and order_copy_email:
        background.add_task(send_buyer_copy, order_copy_email, ctx, pdf_bytes, filename)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_order_email.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/email/order_email.py backend/tests/test_order_email.py
git commit -m "feat: add order email content and background scheduling"
```

---

### Task 5: Wire scheduling into the orders route

**Files:**
- Modify: `backend/app/routers/orders.py` (import near line 24-28; body after the cert-save block, ~line 357, before the conflict-check block at line 363)

- [ ] **Step 1: Add the import**

In `backend/app/routers/orders.py`, add to the imports (after line 25 `from app.geo import conflict`):

```python
from app.email import order_email
```

- [ ] **Step 2: Schedule the emails after the PDF/cert are handled**

In `submit_order`, immediately **before** the `if order.is_new_account:` block (line 363), insert:

```python
    # Email the admin a copy of every order, and the buyer a copy when they
    # opted in. Background tasks (like the conflict check below) so a slow or
    # failed Gmail never blocks the buyer's confirmation. The attachment is the
    # in-memory, card-free PDF — so it sends even if the disk save above failed.
    email_ctx = {
        "short_id": str(order.id)[:8],
        "season_code": order.season_code,
        "season_label": mapping.season_label(order.season_code),
        "buyer_name": order.buyer_name,
        "total_qty": total_qty,
        "total_amount": total_amount,
    }
    order_email.schedule_order_emails(
        background,
        order_copy=payload.terms.order_copy,
        order_copy_email=str(payload.terms.order_copy_email) if payload.terms.order_copy_email else None,
        ctx=email_ctx,
        pdf_bytes=pdf_bytes,
        filename=filename,
    )
```

- [ ] **Step 3: Run the full backend suite to verify nothing broke**

Run: `cd backend && python -m pytest -v`
Expected: PASS — all existing tests plus the new ones. (No route regression; the scheduling logic itself is covered by `test_order_email.py`.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/orders.py
git commit -m "feat: schedule order-copy and admin emails on order submit"
```

---

### Task 6: Env + docs

**Files:**
- Modify: `.env.example` (lines 38-44), `CLAUDE.md`, `docs/SETUP.md` (line ~225)

- [ ] **Step 1: Update `.env.example`**

Replace lines 38-44 of `.env.example`:

```
# Email (order copies + admin notice). Gmail / Google Workspace SMTP.
# Blank host/user/pass = mail disabled (app logs a warning, orders still work).
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=wholesale@wooden-ships.com
SMTP_PASS=                       # Google App Password (not the account password)
MAIL_FROM=wholesale@wooden-ships.com   # From address; defaults to SMTP_USER if blank
ADMIN_EMAIL=wholesale@wooden-ships.com # gets a copy of every order
```

- [ ] **Step 2: Update `CLAUDE.md`**

In the stack section, change the Email line from:

```
- Email: `fastapi-mail` (SMTP), configurable recipients.
```
to:
```
- Email: stdlib `smtplib` (SMTP, sent via FastAPI BackgroundTasks — chosen over `fastapi-mail` because the submit flow is synchronous). Order copies to the buyer (opt-in) + an admin notice on every order; both from `wholesale@wooden-ships.com`.
```

In the "Things to confirm with Prada" section, change:
```
- Admin email recipient(s).
```
to:
```
- ~~Admin email recipient(s)~~ — confirmed 2026-07-22: `wholesale@wooden-ships.com` (reps' orders already land there; it's also the From address).
```

- [ ] **Step 3: Correct the stale card-data claim in `docs/SETUP.md`**

Around line 225, replace:
```
**These PDFs contain full card details for manual processing.** The folder is git-ignored and never served by the web server — handle the files per card-data policy and delete them after processing.
```
with:
```
The folder is git-ignored and never served by the web server. The PDF renders the payment **method** only (e.g. "Card on file") — no card number, name, or CVV ever reaches the template (see `backend/app/pdf/template.html`), so the same PDF is safely emailed to the buyer/admin.
```

- [ ] **Step 4: Commit**

```bash
git add .env.example CLAUDE.md docs/SETUP.md
git commit -m "docs: document SMTP email config and correct PDF card-data note"
```

---

### Task 7: Full verification

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS — all tests green.

- [ ] **Step 2 (optional, manual): live SMTP smoke test**

Only if a real Gmail App Password is available in `.env`. Submit a test order via the form with the "receive a copy" box checked and a reachable address; confirm both `wholesale@wooden-ships.com` and the buyer address receive the PDF. Then delete the test order (see `docs/SETUP.md` §5.3). If no credentials are set, confirm the backend logs `SMTP is not configured` warnings and the order still returns `201`.

---

## Self-Review

**Spec coverage:**
- Schema fields + validator → Task 1. ✅
- Config (SMTP settings, disabled-gracefully, sender/admin) → Task 2. ✅
- `mailer.py` transport + unconfigured no-op → Task 3. ✅
- `order_email.py` content builders + orchestrators + `schedule_order_emails` (admin always / buyer opt-in) → Task 4. ✅
- Route wiring after commit, in-memory card-free PDF, background tasks → Task 5. ✅
- Error handling (unconfigured, send failure, opted-in-no-email, disk-save-failed) → covered by Tasks 2-4 tests + Task 5 comment. ✅
- Email content (admin every order; buyer opt-in; no card fields) → Task 4 tests. ✅
- Env + CLAUDE.md + SETUP.md doc updates → Task 6. ✅
- Test plan (schema/mailer/content/schedule) → Tasks 1,3,4 (route branching unit-tested via `schedule_order_emails` rather than a heavy HTTP test — noted intentionally). ✅

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✅

**Type consistency:** `schedule_order_emails(background, *, order_copy, order_copy_email, ctx, pdf_bytes, filename)` signature matches its call in Task 5. `send_admin_copy(ctx, pdf_bytes, filename)` / `send_buyer_copy(to, ctx, pdf_bytes, filename)` match their `add_task` usages and tests. `mail_configured` / `mail_sender` used consistently in `mailer.py` and tests. `ctx` keys (`short_id`, `season_code`, `season_label`, `buyer_name`, `total_qty`, `total_amount`) are identical in Task 4 builders, Task 4 tests, and the Task 5 `email_ctx`. ✅
