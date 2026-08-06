# Development environment

A second copy of the app for testing against **real customer data** without
touching anything real. Runs alongside production on the same machine.

|                        | Production            | Development                  |
|------------------------|-----------------------|------------------------------|
| URL                    | `:8082`               | `:8083`                      |
| Compose project        | `wholesale-order-entry` | `wholesale-dev`            |
| Database volume        | `..._pgdata`          | `wholesale-dev_pgdata_dev`   |
| Order PDFs / uploads   | `output/`             | `output-dev/`                |
| Salesforce **reads**   | live                  | **live** (real accounts, products, territories) |
| Salesforce **writes**  | allowed               | **blocked**                  |
| Outbound email         | real recipients       | **redirected to one inbox**  |

## Start it

```bash
cp .env.dev.example .env.dev      # then edit: MAIL_REDIRECT_TO + secrets
docker compose -f docker-compose.dev.yml --env-file .env.dev up -d --build
# → http://localhost:8083
```

Stop it with the same `-f`/`--env-file` pair and `down`. Add `-v` to throw the
dev database away and start clean.

`.env.dev` is gitignored, like `.env`.

To put it online for reviewers instead of running it locally, see
[`deploy/dev-on-vm.md`](deploy/dev-on-vm.md).

## Telling them apart

The two sites are identical to look at, so dev shows a dark red **DEVELOPMENT**
bar across the top of every page — the order form, `/admin` and the signing
page. Production shows nothing at all.

The bar is driven by `GET /api/health`, which reports `env` derived from the
safety switches rather than from a label, so an environment cannot claim to be
dev while still able to reach real people. It also names what is neutered
("email goes to the test inbox · Salesforce writes are blocked").

## The safety switches

They live in `.env.dev`. They are what make it safe to point a dev environment
at live customer data, and **both must stay blank in production `.env`**.

### `DEV_BUYER_EMAIL` / `DEV_REP_EMAIL` (and `MAIL_REDIRECT_TO`)

Recipients are swapped by role, so a dev send keeps the shape of a real one —
buyer in To, rep in Cc:

| Email at submit | To | Cc |
|---|---|---|
| Admin notice | `DEV_REP_EMAIL` | — |
| Order copy | `DEV_BUYER_EMAIL`, `DEV_REP_EMAIL` | — |
| Signature request | `DEV_BUYER_EMAIL` | `DEV_REP_EMAIL` |

An address counts as a rep if it appears in the sheet's Email tab or equals
`ADMIN_EMAIL`; everyone else is a buyer. If the sheet cannot be read, everyone
is treated as a buyer — the wrong test inbox, never a real one. A role left
blank falls back to `MAIL_REDIRECT_TO`, then to the other role, so a
half-configured dev environment still cannot mail a real person.

`MAIL_REDIRECT_TO` on its own is the simpler catch-all: one inbox for
everything.

Either way the message is rewritten like this:

```
Subject: [DEV → rande@randecohen.com] New wholesale order  WS-4f21
To:      you@wooden-ships.com
```

The body and the HTML part both get a banner naming the intended To and Cc, so
a redirected email can never be mistaken for a real one. Cc is rewritten rather
than dropped, so the message keeps its production structure — what changes is
only who receives it.

Enforced in `app/email/mailer.py:send_email` — the one place an address becomes
a delivery. All five callers (order copies, admin notice, signature requests,
conflict emails, the admin email modal) go through it, and a new caller inherits
the behaviour without having to know about it.

### `SALESFORCE_READONLY=1`

Blocks the only two writes the app makes to the live org:

- **Accept** an order in `/admin` → creating the Kugamon sales order
- **Create account** → creating the Salesforce Account

Both raise `SalesforceReadOnly`, which the admin API turns into a 400 with a
plain explanation rather than a 502 that looks like an outage. Enforced in
`app/salesforce/client.py` at `create_sales_order()` and `create_account()`.

Reads are untouched: buyer lookup, products, price books, territories, and the
`Written_By__c` picklist all return real data, which is the point — the dev
environment behaves like production for everything except the parts that escape.

## What is still shared

- **Google Sheets.** Dev reads the same region/rep sheet. Reads only, but a sheet
  edit affects both environments at once.
- **The Salesforce org.** Read-only from dev, but dev traffic still counts
  against API limits.
- **SMTP.** Dev sends through the same mailbox; only the recipient changes.

## What is NOT protected

- **Card data.** A card typed into the dev form is stored and encrypted exactly
  as production does. Use test card numbers.
- **Sheet writes.** Nothing in the app writes to the sheets today; if that
  changes, it needs a guard of its own like the two above.
