# Reply Tracking — Closing the Loop on Conflict & Tax-Cert Emails

**Status:** Design / not yet built · **Drafted:** 2026-07-25 · **Owner:** admin dashboard team
**Touches:** `frontend/src/admin/OrderTable.jsx`, `backend/app/routers/admin.py`, `backend/app/routers/send_email.py`, `backend/app/db/models.py`, a new inbound-mail service.

## The problem

When the admin clicks **Generate email** on a row and sends it, the dashboard stamps a
timestamp (`conflict_email_sent_at` / `tax_cert_email_sent_at`) and the cell flips to
**"Email Sent ✓ waiting for the response."**

That is the end of the state machine. There is **no inbound handling.** When the rep
replies *"not a conflict"* or the customer emails back their resale certificate, nothing
flows back into the system. The row sits at "waiting" forever and the actual answer lives
in someone's inbox. Whoever works the dashboard has to remember, cross-check their mail,
and mentally track which of these are actually done.

We want the row to **close by itself** — or at least offer a one-click close — once the
requested information comes back.

## Two cases that look the same but aren't

The conflict cell and the tax-cert cell both show "waiting for the response," but what
"resolved" *means* is different for each, and that difference drives the whole design.

| | Conflict | Tax certificate |
|---|---|---|
| What comes back | A **decision** in free text ("they're a different segment, go ahead") | A **document** (a state resale certificate, usually a PDF/image attachment) |
| What we must record | An outcome: `cleared` / `real_conflict` (+ note) | The **file itself**, saved to secure storage, `cert_filename` set |
| Is an LLM useful? | **Yes** — interpreting a free-text reply is exactly its strength | **Mostly no** — the valuable event is "a certificate is attached," a deterministic check. A True/False does *not* put the document on the order. |
| Money/compliance stakes | A territory-selling decision — **don't auto-commit** | Tax ID on the doc — must land in secure storage, never an inbox |

The takeaway: **the LLM is ~10% of the work, and only clearly earns its place on the
conflict side.** The load-bearing engineering is inbound-email capture and correlation,
which both cases share.

## Goals / non-goals

**Goals**
- A row visibly closes once the requested info arrives, without hand-tracking.
- The tax certificate that comes back by email ends up **on the order**, in the same
  secure storage as form-uploaded certs — not stuck in a mailbox.
- Never hand a territory-selling decision to a model unattended.

**Non-goals**
- No general-purpose email client in the admin UI. We read replies to *these* threads only.
- No change to how the *outbound* draft/send flow works (`send_email.py` stays as is).
- No storing of raw inbound email bodies long-term beyond what's needed to show the admin
  why a suggestion was made.

## Phasing — ship value before the hard part

The inbound-email pipeline is a real feature with an external moving part. The manual
close is not. Do them in that order so the loop is closed *today* and the automation
layers on top without blocking.

### Phase 1 — Manual close (no external dependencies)

Everything here is a small, self-contained slice. It fully resolves the conflict case and
gives the tax-cert case its real fix (the document), independent of any email plumbing.

**1a. "Mark resolved" on the conflict cell.**
- New columns on `Order`: `conflict_resolution` (`nullable` enum-ish text: `cleared` /
  `real_conflict`), `conflict_resolved_at`, `conflict_resolution_note` (text).
- New endpoint: `POST /api/admin/orders/{id}/conflict-resolution`
  `{ outcome: "cleared" | "real_conflict", note?: str }` → stamps the three columns.
- `_row()` in `admin.py` exposes `conflictResolution`, `conflictResolvedAt`,
  `conflictResolutionNote`.
- UI: once `conflictEmailSent` is true, the cell shows a small **Mark resolved** control
  (two choices + optional note). After it's set, the cell reads **Resolved ✓ — cleared**
  (green) or **Real conflict** (red), with the note on hover. This *fully* handles conflict.

**1b. "Upload certificate" on the tax-cert cell.** — the real fix for that side.
- New endpoint: `POST /api/admin/orders/{id}/certificate` (multipart file upload),
  admin-only. Validates type/size exactly like the order-form upload path, writes into
  `settings.pdf_output_dir` (the same secure `output/orders` store), sets `cert_filename`.
- No new "resolved" concept needed for tax cert — **the cert's presence _is_ the
  resolution.** The existing cell logic already flips to the **Open** link the moment
  `hasCertificate` is true.
- Reuses the existing `download_certificate` streaming route unchanged.

> **Golden-rule check:** the uploaded cert carries a tax ID, so it must land in
> `pdf_output_dir` (outside the web root, streamed only through the admin route), never in
> a public/static path. This mirrors the form-upload handling — see CLAUDE.md golden rule
> #1 spirit and `admin.py` module docstring.

### Phase 2 — Inbound email + AI auto-suggest (the automation)

Now layer detection on top of the manual close. The manual controls remain as the
fallback and the confirmation surface.

## The inbound pipeline (Phase 2)

Three problems, in order of difficulty: **capture → correlate → classify.**

### 1. Capture — get the replies into the system

We're on Gmail (`SMTP_HOST=smtp.gmail.com`). Two realistic options:

| Option | Latency | Setup cost | Notes |
|---|---|---|---|
| **IMAP poll** of `wholesale@` on a schedule | minutes | low — a cron loop + `imaplib` | **Start here.** No cloud project, no OAuth dance. |
| **Gmail API + `watch` (Pub/Sub push)** | seconds | high — GCP project, Pub/Sub topic, OAuth | Upgrade path if near-real-time ever matters. |

Recommend **IMAP polling** run from a scheduled task (a small backend worker or a cron
that hits an internal endpoint). A few minutes of lag is irrelevant here — reps take hours
or days to reply.

### 2. Correlate — which order does a reply belong to?

**Do not parse the subject line.** It's admin-editable ("CONFLICT Inquiry — {store}") and
reps mangle subjects on reply.

**Use a plus-addressed reply-to carrying the order id.** When the admin sends a draft for
order `abc123`, set the envelope so replies come back to:

```
wholesale+abc123-conflict@wooden-ships.com
wholesale+abc123-taxcert@wooden-ships.com
```

Gmail delivers `wholesale+anything@` to the same `wholesale@` inbox, but the `+abc123-kind`
token tells us **exactly** which order and which flow the reply is for — no guessing, no
NLP needed for routing. The poller reads the `Delivered-To` / `To` header, extracts the
token, and looks up the order.

> This requires threading the order id + kind into the outbound send. `send_email.py`
> already receives `orderId` + `kind`; we'd have it set the `Reply-To` header accordingly.

### 3. Classify — is it resolved?

Only the **conflict** flow needs the model. Sweep orders where
`conflict_email_sent_at IS NOT NULL AND conflict_resolved_at IS NULL`, pull the new
inbound message(s) in that thread, and ask the model:

```json
{
  "resolved": true,
  "outcome": "cleared",              // "cleared" | "real_conflict" | "unclear"
  "confidence": 0.86,
  "reason": "Rep wrote 'different customer base, no objection — proceed.'"
}
```

- **Model:** Claude **Haiku 4.5** is plenty for a resolved/not-resolved read and cheap.
  (This shop's stack is Anthropic-adjacent already; prefer it over OpenAI for vendor
  consistency. See `claude-api` skill for current model IDs/pricing before wiring it.)
- **Human-in-the-loop is mandatory for conflict.** The model **proposes**; it never flips
  the state on its own. A territory-selling decision made off a misread *"well, maybe…"* is
  a real-money mistake. The cell surfaces:
  *"AI suggests: Resolved — cleared (rep said …)"* with a one-click **Confirm** that runs
  the same `POST …/conflict-resolution` endpoint from Phase 1a. `unclear` → no suggestion,
  stays "waiting."

For **tax cert**, skip the LLM: the poller checks whether the inbound reply carries a
PDF/image attachment. If it does, save it via the same code path as Phase 1b's upload
endpoint (→ `cert_filename` set → cell auto-flips to **Open**). Attachment presence is a
deterministic signal; no model call required. (An LLM could *also* sanity-check "is this
actually a resale certificate vs a random PDF," but that's optional polish, not core.)

## Data model summary

New columns on `Order` (Alembic migration):

| Column | Type | Set by |
|---|---|---|
| `conflict_resolution` | text (`cleared` / `real_conflict`), nullable | Phase 1a endpoint / Phase 2 confirm |
| `conflict_resolved_at` | timestamptz, nullable | same |
| `conflict_resolution_note` | text, nullable | same |
| *(tax cert reuses existing `cert_filename`)* | — | Phase 1b upload / Phase 2 attachment capture |

Optional Phase 2 auditing: a small `inbound_reply` table (order_id, kind, received_at,
from, snippet, ai_outcome, ai_confidence) so the admin can see *why* a suggestion appeared.
Keep only a snippet, not the full body — minimize stored PII.

## API surface (new)

- `POST /api/admin/orders/{id}/conflict-resolution` — `{outcome, note?}` (Phase 1a)
- `POST /api/admin/orders/{id}/certificate` — multipart cert upload (Phase 1b)
- *(Phase 2, internal)* a scheduled worker or `POST /api/admin/poll-replies` that the
  cron hits; not user-facing.

## UI changes (`OrderTable.jsx`)

- **Conflict cell:** after "Email Sent ✓", render a **Mark resolved** control; after
  resolution, render the outcome chip (green cleared / red real-conflict) with the note on
  hover. Phase 2 slots an **AI suggests … [Confirm]** banner in the same spot.
- **Tax-cert cell:** add an **Upload cert** button next to "Email Sent ✓ waiting…". On
  success the existing `hasCertificate` → **Open** path takes over with no further work.

## Open questions

- Retention of inbound snippets — how long, and does legal/compliance care?
- Should a confirmed `real_conflict` auto-influence the Accept/Decline decision, or just
  inform it? (Lean: inform only — keep the decision explicit.)
- Do we want the AI suggestion to also draft a reply, or purely classify? (Lean: classify
  only for v1.)
- Which mailbox identity sends — does using `Reply-To: wholesale+token@` interfere with any
  existing mail rules on `wholesale@`?

## Recommended build order

1. **Phase 1a + 1b** — manual "Mark resolved" (conflict) and "Upload certificate" (tax
   cert). Closes the loop today, zero external dependencies, small diffs.
2. **Phase 2 capture + correlate** — IMAP poller + plus-address reply-to + attachment
   capture for tax cert (still no LLM).
3. **Phase 2 classify** — Claude Haiku conflict-reply classification as an *admin-confirmed
   suggestion*.
