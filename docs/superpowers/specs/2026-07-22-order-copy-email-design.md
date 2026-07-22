# Order-copy email + admin notification — design

**Date:** 2026-07-22 · **Status:** approved for planning
**Touches:** `backend/app/schemas/order.py`, `backend/app/config.py`, `backend/app/email/`, `backend/app/routers/orders.py`, `.env.example`, docs

## Problem

The order form now has an opt-in checkbox — *"I would like to receive a copy of
this order form."* — plus a conditional **"Email address for order copy"** field
(added in `frontend/src/components/TermsSignature.jsx`, state `terms.orderCopy` /
`terms.orderCopyEmail` in `App.jsx`). When a buyer opts in, submitting the order
should email them a copy.

Two facts make this bigger than a one-liner:

1. **The app sends no email at all today.** `POST /api/orders` validates →
   renders the PDF → saves to disk → commits. There is no mailer, no SMTP config,
   and no mail dependency. Email was deferred (`docs/SETUP.md`).
2. **The backend currently drops the new fields.** The `Terms` schema has only
   `signature_name`, `signature_date`, `accepted`; Pydantic ignores the extra
   `orderCopy` / `orderCopyEmail` the frontend sends.

While building the mail capability we also fulfil the original PRD goal of
emailing the admin team on every order.

## Decisions (from brainstorming)

| Decision | Choice | Why |
|---|---|---|
| Transport | stdlib **`smtplib`** (STARTTLS, `EmailMessage`) | Submit route is sync + uses `BackgroundTasks`; `fastapi-mail` is async-first and adds friction/deps for no benefit. (CLAUDE.md's stack line said fastapi-mail — we override and note it.) |
| Provider | Gmail / Google Workspace, `smtp.gmail.com:587`, App Password | Account is `wholesale@wooden-ships.com`, already the reps' order mailbox. |
| Sender (`From`) | `wholesale@wooden-ships.com` | Confirmed by PPIC — confirmations go out from this mailbox. |
| Admin recipient | `wholesale@wooden-ships.com` | Confirmed — reps' orders already land here. Resolves CLAUDE.md's `orders@…` guess + the "admin recipient" TBD. |
| Admin email | Sent on **every** order | Fulfils PRD "email admin". |
| Buyer copy | Sent **only when opted in** with a valid email | The feature request. |
| Failure mode | Both sends run as **background tasks after commit**; failures are logged, order always succeeds | A slow/broken Gmail must never fail or delay a valid order. Mirrors the conflict-check pattern already in `orders.py`. |
| Body format | Plain text (v1) | No HTML styling needed yet. |
| Attachment | The existing **card-free** order PDF (`pdf_bytes`, in memory) | `template.html` renders payment *method* only — no number/name/CVV — so the buyer can safely get the same PDF as admin. |

## Architecture

Two small modules, transport separated from content:

- **`backend/app/email/mailer.py`** — transport only.
  `send_email(to: str, subject: str, body: str, attachments: list[tuple[str, bytes, str]]) -> bool`
  Builds an `EmailMessage`, connects `smtplib.SMTP(host, port)`, `starttls()`,
  `login()`, `send_message()`. Guard: if SMTP is not configured (host/user/pass
  blank) it logs a warning and returns `False` **without connecting**. Any
  exception is caught, logged, returns `False`. Contains no order knowledge.

- **`backend/app/email/order_email.py`** — content only.
  Builders that take a plain context dict and return `(subject, body)`:
  `admin_email(ctx)` and `buyer_email(ctx)`. Plus two orchestrators that the
  background tasks call, each assembling the attachment and delegating to
  `mailer.send_email`:
  `send_admin_copy(ctx, pdf_bytes, filename)` and
  `send_buyer_copy(to, ctx, pdf_bytes, filename)`.

### Data flow

```
POST /api/orders
  … validate, render pdf_bytes (card-free), db.commit() …
  ctx = {short_id, buyer_name, season_code, season_label, total_qty, total_amount}
  filename = order_pdf_filename(...)

  background.add_task(order_email.send_admin_copy, ctx, pdf_bytes, filename)      # always
  if terms.order_copy and terms.order_copy_email:                                 # opt-in
      background.add_task(order_email.send_buyer_copy,
                          terms.order_copy_email, ctx, pdf_bytes, filename)
  return confirmation
```

Background tasks receive only plain data + `pdf_bytes` — no ORM object or DB
session (the request session is closed by the time they run). Because
`pdf_bytes` lives in memory, emails still send even if the earlier disk save of
the PDF failed.

## Schema change

`backend/app/schemas/order.py`, extend `Terms`:

```python
class Terms(CamelModel):
    signature_name: str = ""
    signature_date: date | None = None
    accepted: bool = False
    order_copy: bool = False
    order_copy_email: EmailStr | None = None

    @model_validator(mode="after")
    def _require_copy_email(self):
        if self.order_copy and not self.order_copy_email:
            raise ValueError("order_copy_email is required when order_copy is set")
        return self
```

`EmailStr` (already imported) validates the address; the validator enforces
presence when opted in. Camel aliases `orderCopy` / `orderCopyEmail` come from
the existing `alias_generator=to_camel`. `model_validator` is added to the
pydantic import.

## Config change

`backend/app/config.py` new settings (defaults keep the app working with no mail
config):

```python
smtp_host: str = ""
smtp_port: int = 587
smtp_user: str = ""
smtp_pass: str = ""
mail_from: str = ""                     # falls back to smtp_user when blank
admin_email: str = "wholesale@wooden-ships.com"

@property
def mail_configured(self) -> bool:
    return bool(self.smtp_host and self.smtp_user and self.smtp_pass)

@property
def mail_sender(self) -> str:
    return self.mail_from or self.smtp_user
```

`.env.example` gains the matching block (already sketched in CLAUDE.md's env
list; wire it up for real):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=wholesale@wooden-ships.com
SMTP_PASS=
MAIL_FROM=wholesale@wooden-ships.com
ADMIN_EMAIL=wholesale@wooden-ships.com
```

## Email content

Plain text; both attach the PDF as `application/pdf` named by
`order_pdf_filename()`.

**Admin** → `settings.admin_email`, every order:
- Subject: `New wholesale order — {buyer_name} ({season_code}) — {total_qty} pcs`
- Body: buyer name, season label, total qty, total amount, order short id, "PDF attached."

**Buyer copy** → `order_copy_email`, opt-in:
- Subject: `Your Wooden Ships wholesale order — {season_label}`
- Body: short thank-you, the same order summary, "Your order copy is attached."
- No card fields, no internal-use fields.

## Error handling / edge cases

| Case | Behavior |
|---|---|
| SMTP not configured | `mailer.send_email` logs a warning, returns `False`, never connects. Order unaffected. |
| Send raises (auth, network, bad address) | Caught, logged with order short id for follow-up. Order unaffected. |
| `order_copy` true, email blank/invalid | `422` at request validation, before anything persists. |
| PDF disk-save failed earlier | Emails still send — attachment is the in-memory `pdf_bytes`. |
| Buyer opts out | No buyer email; admin email still sends. |

## Testing (pytest, mock `smtplib.SMTP`)

1. **Schema** — `order_copy=True` with no/invalid email → `ValidationError`;
   `order_copy=True` + valid email OK; `order_copy=False` + blank OK; camel
   aliases parse.
2. **Mailer** — with a mocked SMTP: builds a message with correct
   `From`/`To`/`Subject` and a PDF attachment; calls `starttls`/`login`/`send`.
   When unconfigured: returns `False` and never instantiates `SMTP`.
3. **Content builders** — `admin_email`/`buyer_email` subjects and bodies contain
   buyer, season, totals; contain no card fields.
4. **Route** — patch `order_email.send_admin_copy`/`send_buyer_copy`: admin task
   is always scheduled; buyer task scheduled only when opted in; buyer task gets
   the `order_copy_email` address.

## Out of scope (v1)

- HTML/branded email templates.
- Retry/queue for failed sends (a failure is logged, not retried).
- Sending the tax-exemption certificate or any internal-use data to the buyer.
- Configuring the real Gmail App Password (ops step, not code).

## Docs to update alongside

- `.env.example` — the SMTP block above.
- `CLAUDE.md` — note `smtplib` chosen over `fastapi-mail`; resolve the "Admin
  email recipient(s)" open item to `wholesale@wooden-ships.com`.
- `docs/SETUP.md` — correct the stale line claiming order PDFs "contain full card
  details"; they render the payment method only.
