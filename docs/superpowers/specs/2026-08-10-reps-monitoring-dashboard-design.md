# Rep order-monitoring dashboard — design

**Status:** approved · **Date:** 2026-08-10

A read-only page at `/reps` where a sales representative signs in and sees the
orders that belong to them: when it came in, whether the buyer has signed, and
whether the office has accepted it. Reps send nothing and change nothing.

> **Revised 2026-08-11 — the name is typed, not picked.** The sign-in name is a
> text box and reps type their **first** name; `reps_auth.resolve_name()` turns
> what was typed into the roster name (case and spacing ignored, a full name
> still accepted, an ambiguous first name resolving to nobody so two Michaels
> both have to type a full name). Everything below still holds: the roster name
> is what lands in the session, so §2's rule that only a `REP_NAMES` entry can
> hold a session is unchanged, and the throttle is keyed on the resolved rep so
> re-capitalizing the name buys no extra guesses. `GET /names` survives for the
> office but the page no longer calls it.

## 1. Why this is not "/admin with fewer columns"

`/admin` returns the whole customer book with card name, card last 4, expiry,
payment method, the nearby-stockist conflict verdict and its email thread,
Salesforce ids, and dollar totals. A rep needs eleven columns of their own
orders.

Hiding columns in the browser would still ship every one of those fields to the
rep's machine. So the split is server-side: a separate router with its own
session key and its own row serializer that never touches the sensitive
columns. The admin payload cannot leak into the rep page because it is never
built there.

## 2. Authentication

**One password per rep** (revised 2026-08-10 — see §2a for what it replaced).
Hashes live in `REPS_PASSWORD_HASHES`, a JSON object keyed by the rep's
normalized name, built in one command:

```
docker compose exec backend python -m app.reps_auth "Aviva Landin=…" "Denise Arnett=…" …
```

Normalized keys keep spaces out of the `.env` value and make the lookup immune
to spacing and case differences. Same pbkdf2-hmac-sha256 and the same base64
wrapper that keeps `$` out of the value (see `app/admin/security.py`). The value
is parsed defensively in `app/reps_auth.py` rather than typed as a dict on
`Settings`: a typo in a setting only `/reps` reads must not crash the whole app,
so a malformed value disables rep sign-in and nothing else.

A name must be in **both** `REP_NAMES` and the hash map, so removing a departing
rep from the roster locks them out even if their hash is still in `.env`.

The login roster is a constant in `app/reps_auth.py`:

```python
REP_NAMES = ("Aviva Landin", "Denise Arnett", "Jason Hilsenrad", "Kitty Tally",
             "Michael Young", "Rande Cohen", "Vickie Wilde")
```

Hardcoded rather than read from the region/rep sheet on purpose: it is a
security boundary — only these names can sign in — and the sheet's Email tab
carries rows that are not reps. Adding a rep is a one-line change.

| Route | Auth | Behaviour |
|---|---|---|
| `GET /api/reps-portal/names` | none | the roster; was the dropdown list, unused by the page since 2026-08-11 |
| `POST /api/reps-portal/login` | none | `{name, password}`; name must resolve to a `REP_NAMES` entry, password verified constant-time |
| `POST /api/reps-portal/logout` | none | pops the rep key |
| `GET /api/reps-portal/session` | none | `{authenticated, name}` |
| `GET /api/reps-portal/orders` | rep | the rep's orders |
| `GET /api/reps-portal/orders/{id}/pdf` | rep | that order's PDF, if the rep owns it (§4b) |

`session["rep"]` holds the signed-in name and is a **separate key** from
`session["admin"]` inside the same signed cookie. A rep session fails
`require_admin`; an admin session fails `require_rep`. Neither can become the
other and no new middleware is needed.

Logout pops only its own key rather than calling `session.clear()`, so signing
out of the rep page in a browser that also has an admin session does not sign
the admin out as a side effect.

A wrong name and a wrong password return the same 401 text. Failures are logged
with the name (never the password) — the only thing that makes a run of
failures diagnosable. Successful sign-ins are logged too, which is the audit
trail a shared password could not provide.

### 2a. Why not one shared password

The first build used a single `REPS_PASSWORD_HASH` for all seven reps. It was
rejected on review, correctly: the login is a **name dropdown**, so the shared
password gave no identity at all. Any rep could select a colleague's name, type
the password everybody had, and read that colleague's entire book — no pattern
to spot, no guessing, two clicks. `test_reps_portal` pins the fix:
`test_a_reps_password_does_not_open_another_reps_dashboard`.

Passwords are `word-NN` (e.g. `harbor-42`), chosen by the business. The words
are unrelated to the reps' names, which is the property that matters — knowing
your own reveals nothing about anyone else's, so there is no order to permute.

At roughly a million combinations, `word-NN` is far beyond hand-guessing but
within reach of a script given unlimited attempts — so both logins are
throttled (`app/login_guard.py`, added 2026-08-10). Two rolling-window
counters, either of which trips with a 429 and a `Retry-After`:

| Counter | Limit | Stops |
|---|---|---|
| client IP | 10 / 15 min | one machine grinding through every rep in turn |
| identity (rep name, or `"admin"`) | 20 / 15 min | a distributed attempt on **one** account, which the IP counter cannot see |

The identity counter is not optional: `X-Forwarded-For` is caller-supplied, so
the IP counter alone is evadable. Its cost is that someone can deliberately
lock one rep out for a few minutes — a nuisance, not a breach, and it clears
itself. A successful sign-in clears both, so a rep who mistypes and then
remembers is not locked out by their own attempts. The check runs **before**
password verification, so a locked-out caller cannot distinguish a right guess
from a wrong one.

Client IP comes from the first `X-Forwarded-For` entry: nginx proxies
everything, so `request.client.host` is the proxy and every caller would
otherwise share one counter — the first ten failures anywhere would lock out
the whole team.

In-process, so like the reminder sweep it assumes a single backend replica; a
second would double the allowance. Fine today, but it belongs in Postgres or
Redis if this is ever scaled out.

## 3. Which orders belong to a rep

The rule already exists and already decides who receives the order email:

```python
mine    = sheets_client.rep_email_for_writer(signed_in_name)
belongs = sheets_client.rep_email_for_order(o.order_written_by, o.sales_territory)
```

An order is the rep's when those two addresses match, compared casefolded.
Reusing `rep_email_for_order` inherits the 2026-08-06 decision for free —
Written By is the authority, the Sales Territory owner is the fallback for
customer-filled orders — and guarantees the dashboard and the rep's inbox can
never disagree, because both consult the same function.

When `mine` is `None` — the rep's name does not resolve to an address in the
sheet — the endpoint returns **zero orders and an explanatory message**, never
the unfiltered list. Fail closed. A test asserts every name in `REP_NAMES`
resolves, so a spelling drift between the constant and the sheet surfaces in CI
rather than as an empty table in front of a rep.

The match is a Google Sheet lookup, so it cannot be a SQL `WHERE`. Rows are
selected newest-first with the optional status filter applied in SQL, then
filtered in Python and the response capped at 500. There is deliberately no SQL
`LIMIT` before the ownership filter: it would truncate the candidate set and
silently drop a rep's older orders. At current volume this is a non-issue; it is
the thing to revisit if the orders table reaches tens of thousands of rows.

## 4. The payload

`GET /api/reps-portal/orders?status_filter=` →
`{"rep": name, "message": str | null, "counts": {...}, "orders": [...]}`

A dedicated `_rep_row()`, **not** `admin._row()`. It emits exactly these keys:

```
id, shortId, createdAt, seasonCode, totalQty, shipWindow, accountName, totalAmount,
orderWrittenBy, salesTerritory, notes, status, statusReason, statusAt,
signatureRequested, signatureEmailSent, signatureEmail, signatureSignedAt,
signatureName, signatureEdited, origTotalQty
```

Two deliberate omissions:

- **No PRE-signature money.** `totalAmount` is sent (the Value column, added
  2026-08-10 — v1 sent a rep no money at all). `origTotalAmount` is not:
  `signatureEdited` is computed server-side by comparing the snapshot against
  the current totals, so the rep sees "edited: 40 → 22 pcs" without being told
  what the order was worth before the buyer trimmed it.
- **No card, conflict, certificate or Salesforce fields**, at all.

The route makes no Salesforce call, unlike the admin list, and does not run the
expired-card-copy purge — that is the admin page's housekeeping.

## 4b. The order PDF (added 2026-08-10)

`GET /api/reps-portal/orders/{id}/pdf` — the Order ID cell links to it, as on
`/admin`. v1 deliberately had no PDF; the business asked for it afterwards, so
the order id is now in the payload (it was previously withheld precisely
because nothing acted on an order).

Three rules make that safe:

- **Ownership is re-checked server-side** with the same `_owns` used by the
  list. The id in the payload is a lookup key, not a capability.
- **404, never 403**, for an order the rep does not own — a rep must not be able
  to probe which order ids exist outside their own book. The check runs before
  the file is even named.
- **Always the masked copy.** There is no `full=1` here. The admin copy showing
  the whole card number exists for the monitoring team to key into Kugamon;
  nothing on this page needs it, so the parameter simply does not exist.

The traversal guard moved to `pdf_render.safe_output_path` when the second
router needed it — a guard like that should never exist in two copies. It
raises `ValueError` / `FileNotFoundError`; each router maps those to 400 / 404.

## 4a. Metric cards (added 2026-08-10)

Five cards above the table:

| Card | Count | Sub-line |
|---|---|---|
| Total orders | every order of the rep's | total pieces |
| Awaiting signature | link out, not yet signed | `longest N days`, plus `N not sent yet` when non-zero |
| Awaiting review | `status = submitted` | — |
| Accepted | `status = accepted` | — |
| Declined | `status = declined` | — |

The three status cards partition the total exactly; Awaiting signature cuts
across them (an order can await both), so it is rendered apart from the status
group rather than in line with it.

`oldestAwaitingDays` is what makes the awaiting count mean anything — three
links out for two days is healthy, one out for three weeks is a lost order.
Measured from `signature_requested_at` where known, `created_at` otherwise.

**Counts are computed server-side over the rep's whole book, before the status
filter.** That is the whole reason they are not derived in the browser: the
status chips filter server-side, so once one is active the page only holds part
of the book and cards built from the visible rows would read zero. Concretely,
`list_orders` dropped its SQL `WHERE status` — it matches ownership once, counts
that list, then filters it in Python. Same query count.

The counts block is returned even when the rep is unresolvable (all zeroes), so
the page never has to branch on its absence.

**The cards are display only** (decided 2026-08-10, after a clickable version
was built and rejected). The status chips are the single filter control. So the
cards are plain `<div>`s: nothing is clickable, and a `<button>` would inherit
the global dark-fill / white-text / uppercase rule and need three overrides to
undo it. Awaiting signature is therefore not a selectable view — it is a number
to act on, not a filter. Adding it would mean a fifth chip, since it is not an
order status and could not be filtered server-side like the other four.

## 5. Frontend

New `frontend/src/reps/` — `RepsApp.jsx`, `RepLogin.jsx`, `RepMetrics.jsx`,
`RepOrderTable.jsx`, `api.js`. One line in `main.jsx` maps `/reps`; nginx needs
no change because the SPA fallback already covers unknown paths.

Reuses the existing `.admin*` CSS classes so it reads as the same product. The
header is "My orders — <name>" with Sign out.

Columns, left to right: **Date · Order ID · Signature · Season · QTY ·
Ship Window · Account Name · Value · Written By · Sales Territory · Notes ·
Decision**. The Order ID links to that order's PDF (see §4b).

Toolbar: status chips (All / Awaiting review / Accepted / Declined) and
Refresh. All is the default — a rep wants their whole recent book, unlike the
office, which triages the pending queue. No row count (the Total orders card
carries the book size and the active chip says the table is narrowed), no
per-column filters, no Excel export, no reply polling.

Two traps in the shared stylesheet, worth knowing before adding any
button-shaped control here: the global `button` rule is dark-fill **and**
`color: #fff`, so overriding only the background leaves the text invisible on a
light card; and it applies `text-transform: uppercase`, which suits a label but
turns a sub-line into shouting. Both bit the clickable version of the cards.
Not an issue now that they are `<div>`s.

The Signature cell is a small read-only component in `reps/`. The admin version
is not reused: it is 70 lines wrapped around Send-email and Resend buttons a rep
must never see, and threading a read-only flag through a 1074-line file to save
20 lines of markup is a bad trade. `reps/api.js` likewise keeps its own small
fetch wrapper rather than reaching into `admin/api.js` internals.

## 6. Tests

`backend/tests/test_reps_portal.py`:

- a rep session gets 401 from `/api/admin/orders`
- an admin session gets 401 from `/api/reps-portal/orders`
- login rejects a name outside `REP_NAMES`, and rejects a wrong password, with
  the same message for both
- one rep's password does not open another rep's dashboard; a roster name with
  no hash entry cannot sign in; a hash entry off the roster is ignored; a
  malformed `REPS_PASSWORD_HASHES` disables sign-in without breaking `/api/health`
- ownership: a rep-written order goes to the writer's rep, not the territory
  owner; a customer-filled order falls through to the territory owner
- an unresolvable rep email yields an empty list, not the full list
- **payload allowlist:** assert the exact key set of a rep row, so a future
  edit to `_rep_row()` cannot quietly reintroduce card or conflict data
- counts cover every card, exclude another rep's orders, and — the one that
  matters — stay whole-book while a status filter narrows the rows

## 7. Out of scope for v1

No emailing of any kind, no accept/decline, no tax certificate, no
conflict information, no card data, no dollar totals, no Excel export.

## 8. Open questions

1. **Split orders.** `split_with` names a second rep, who does not see the order
   under the current rule. If a split partner should see it, the rule becomes a
   union and "my orders" stops meaning one thing — worth deciding once reps have
   used the page.
2. **Credential sharing.** Per-rep passwords stop a rep opening a colleague's
   dashboard; they cannot stop two reps agreeing to share one. Only real SSO
   does. The org already runs Google Workspace and the rep contact sheet
   already maps names to addresses, so Google sign-in is the natural next step
   if that ever becomes a live concern.
