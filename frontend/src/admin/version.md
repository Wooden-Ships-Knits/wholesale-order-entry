# Version history

Released versions of the Wooden Ships wholesale order form.

One entry per version, newest first. A version is cut by tagging `main`:

```
git tag -a v1.1 main -m "Version 1.1 — <one line>"
git push origin v1.1
```

The tag is the record of what shipped; this file is the record of what changed
and why. Add the entry in the same commit that cuts the tag, so the two can
never disagree about what a version contained.

**Dates are the tag date, not the merge date.** Work sits on `main` for a while
before it is released, and "when did this reach production" is the question
anyone reading this file is actually asking.

---

## v1.1 — 2026-08-29

### New

- **Order monitoring — "Cleared" button on Potential conflict.** When a rep
  sends several orders for the same new store, every one of them raises the
  same conflict. Email the rep once, then clear the rest with this button
  instead of emailing them again for each order.

- **Order monitoring — "Cleared" button on Tax certificate.** Same idea. A new
  store only sends its resale certificate once, so the other orders can be
  closed without chasing the customer again. The column still shows "No" —
  clearing means "we've stopped asking", not "we have the document".

- **Reps portal — quick link to the order form.** A DOF shortcut in the tab
  row. *(Currently switched off.)*

- **Reps portal — search by brand.** Type a brand name in the Prospects table
  to find shops that already stock it.

- **Sign-in — your browser can now offer to save the password.**

### Fixed

- **Follow-up emails no longer go quiet after a manual send.** Sending a
  signature email by hand used to restart the customer's follow-up clock, so
  chasing someone yourself made the automatic reminders arrive *later* — often
  by two weeks. The schedule now runs from the first request and a manual email
  doesn't move it.

- **No more bursts of reminders.** If an order fell behind, the reminders it
  had missed went out one an hour until it caught up — so a customer could get
  three emails in three hours. Missed reminders are now skipped rather than
  sent late.

- **Order monitoring — Decision column** now shows the date an order was
  accepted, is wider, has a date-range filter, and lists every order instead of
  stopping at 100.

- **Order monitoring — Signature column** now shows a signature when the
  customer filled in the form themselves, instead of looking blank.

- **Maps** stopped showing an "API KEY REQUIRED" watermark. This needs a CARTO
  key added on the server — see `CLAUDE.md`.

### Worth knowing

- Signing links used to last 7 days. Orders placed on 5–6 August were created
  under that old setting, and their links expired before the follow-up schedule
  finished. Links now last 36 days. If an old order has a dead link, resend it
  from the order monitoring page.

---

## v1.0 — 2026-08-28

Commit `d8b2c15`

First tagged version. Everything the wholesale order form did up to this point:
the order form itself, Salesforce product and customer lookup, order minimums,
PDF generation, customer signing links, the admin order monitoring page, the
reps portal, and the stockist conflict check.

---

<!--
Template for the next entry — copy above this line.

## v1.1 — YYYY-MM-DD

Commit `<short sha>`

### Added
-

### Changed
-

### Fixed
-
-->
