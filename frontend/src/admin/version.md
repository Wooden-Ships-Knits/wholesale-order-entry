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

## v1.3 — unreleased

### New

- **Add a new buyer from the Buyer name dropdown.** When an account has more
  than one contact, reps choose the buyer from a dropdown. If the person placing
  the order isn't in it yet, the dropdown now ends with **+ Add new buyer…**,
  which turns it into a text box for typing the name. **Choose from existing
  contacts** underneath switches back to the list.

- **Order monitoring — new Campaign column.** Shows the campaign chosen in
  the form's Internal Use section (Rep non-show order, or Other with its name).
  **Change** lets you correct it or fill it in while the order is awaiting
  review. Once an order is accepted the campaign is on the Salesforce order, so
  it can no longer be changed here. The column has its own filter and is
  included in Export to Excel.

- **Export to Excel now includes the items ordered.** The file has a second
  sheet, **Order items**, with one row per style/colour: the code, style,
  colour, quantity in each size (X/S, S/M, M/L), line quantity, unit price and
  line total. Each row also carries its order's ID, date, account, season and
  status, so the sheet can be filtered or turned into a pivot table on its own.
  It covers the same orders as the Orders sheet, so whatever filters are on
  screen apply to both. The Orders sheet gains a **Styles** column showing how
  many lines each order has.

- **Ship Window turns yellow once the window has opened.** An order still
  awaiting review whose ship window start date has passed is now highlighted,
  so late orders stand out. Hover over the cell to see the date it opened.
  Accepted and declined orders are not highlighted.

- **Reports — new "OO — Open Order" report.** **Run report** pulls the
  Salesforce "Rep Open Order Detail Report" up to today and downloads one zip
  with the Master - OO spreadsheet plus one file per rep
  (e.g. `OO-CA,HI-YTD-261027-Rande.xlsx`) and a House file for the House and
  unassigned territories. An order split with another rep also appears in that
  rep's file, in a **Split orders** section below their own orders with its own
  subtotal. Each order is coloured:
  **yellow** — entered in the last week, make sure nothing is missing;
  **orange** — within its ship window, check the Problem List in case it is
  stuck; **red** — past its ship window, see the Problem List Email. An order
  that fits more than one colour takes the most urgent. The card also lists the
  red orders and how many orders are in each colour.

  Like the hand-made file, the spreadsheet opens grouped: one Total row per
  order, showing the order's territory, dates, account and amount, with the
  **+** button below it opening that order's lines. Orders are sorted by Sales
  Territory, then order number.

  The report's "Order Date up to" filter is set to today automatically, so it
  never needs changing in Salesforce. Unlike the hand-made file, every line
  shows its own product — in the old file each order's first line was blank
  and the product names sat one row lower than their quantities.

### Changed

- **Ship To and Bill To have swapped sides on the order form.** Ship To is now
  on the left and Bill To on the right. The address search on the left fills
  in the shipping address, and the **Same as Ship To** box under Bill To copies
  it into billing. For new accounts that box starts ticked. Typing in a Bill To
  field or searching a different billing address unticks it, so a separate
  billing address is never overwritten.

  Buyer name, Tel, Email and Resale tax ID stay where they were.

- **The DOF link in the reps portal now opens the order form in a new tab**,
  so the rep's dashboard stays open behind it.

- **Reports — Copy button on the output.** Each report card now has a
  **Copy** button beside its Output, which copies the whole recap in one click,
  ready to paste into WhatsApp.

- **The DMM recap now reads like the team's own morning email.** It is
  formatted for WhatsApp: each group's title and each listed account are in
  \*bold\*, and the bullets are plain dashes.
  - **Paid orders** are split by AIR and FCL ("For 3 AIR SOs, we plan to ship
    them on Wed, Oct 28 (LT = 2 days) at the latest"). AIR or FCL comes from
    each order's Estimated Shipment Name in Salesforce.
  - **Each unpaid group** is titled with its season, month and AIR/FCL, for
    example *UNPAID F26 October AIR (10/01 - 10/15)*. It shows the window's
    **Last communication** and **Plan** from the Email Schedule tab, including
    the "Reply to All" follow-ups.
  - **FCL groups, and windows whose emails have run out before the cancel
    date,** list every account instead, as long as the group has 3 SOs or
    fewer. Bigger groups keep the Last communication and Plan lines. Each account shows its rep, its latest
    problem note from the rep's tab, its last email or notice, and its next one
    from the month tab (OCT, NOV, …).
  - **The unpaid section is no longer empty.** The Salesforce report's saved
    date filter had gone stale (it still read 1 July). The report now always
    runs up to the end of next month, so it never needs editing in Salesforce.
  - **Changes to the Email Schedule show up on the next run.** They used to
    wait for a server restart.

- **The DMM and OO reports now go by Bali time.** "Today" is the date in Bali
  (WITA), not the server's clock, which runs on UTC. In the DMM that decides
  which paid SOs count as updated today, the lead times, and which chase
  emails have gone out; in the OO, which orders are yellow, orange or red.
  Before this, a DMM run before 8 am Bali time used yesterday's date.

### Worth knowing

- A buyer added this way is saved on the order only. It is not created as a
  contact in Salesforce, so the next order from that account will not list
  them until someone adds them there.

- Changing an order's campaign does not update the order PDF already on file;
  the PDF keeps the campaign it was submitted with.

- Rebuild both the frontend and the backend. No database change.

---

## v1.2 — 2026-09-05

### New

- **Order monitoring — new "Catalog" tab.** Pick a collection, then tick any
  style/colour to take it off the order form. Use it for the ones that sold
  out, never got made, or were pulled after the line sheet went out — until
  now the only way to stop a customer ordering those was to edit the price
  book in Salesforce, which changes what the whole company sees.

  Ticks save as you make them; there is no Save button. A search box filters
  by style name or product code, and the count beside it tells you how many of
  the collection's style/colours are currently hidden.

  **Nothing is changed in Salesforce**, and orders already placed or already
  out for signature keep their prices and totals — a customer part-way through
  signing will not find their sweater has vanished.

### Fixed

- **The Version tab you are reading had never actually been styled.** A single
  missing bracket in the stylesheet meant every rule written for this page was
  ignored by the browser, along with the widths set for the Decision column on
  the order table. Both now look the way they were written to look.

### Worth knowing

- Hiding is for this web order form only. It does not stop a style being
  ordered any other way, and it does not touch the price book — so it is a
  merchandising choice, not a lock.

- This version adds a database table, so the deploy needs
  `alembic upgrade head` as well as a frontend rebuild.

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
