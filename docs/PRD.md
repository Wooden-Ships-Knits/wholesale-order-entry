# PRD — Wooden Ships Wholesale Order Form

**Version:** 0.1 (draft)
**Owner:** Prada
**Last updated:** 2026-07-13

---

## 1. Overview

Wooden Ships sells knit sweaters wholesale. Today, buyers order via a static PDF/Excel order form (`F26 - WS PDF Order Form.xlsx`) that must be filled in and emailed back manually. This project replaces that with a **web-based order form** that:

- Loads the live product catalog for a selected season/collection from **Salesforce**.
- Auto-fills buyer details from **Salesforce** when the buyer is identified.
- Validates order minimums automatically.
- On submit, **stores the order in PostgreSQL** and **generates a PDF** of the completed order for the admin team. *(Emailing the PDF to admin is deferred — v1 saves the PDF server-side; see §8.)*

The web form must contain **every field and section present in the Excel order form** — nothing is dropped.

## 2. Goals & non-goals

### Goals
- Faster, error-free ordering for wholesale buyers.
- Single source of truth for products and pricing (Salesforce).
- Automatic order-minimum enforcement.
- Structured order records in PostgreSQL for internal reporting.
- Admin receives a clean, print-ready PDF per order by email.

### Non-goals (for v1)
- No online payment capture/charging. Card details are collected on the form (matching the Excel form) and passed to admin for **manual** processing — see §7 Security.
- No buyer self-service account portal / login.
- No inventory/stock availability check (products are made to order).
- No two-way sync writing orders back into Salesforce (v1 stores in PostgreSQL only; can be added later).

## 3. Users

- **Wholesale buyer** — fills and submits the order. May or may not exist in Salesforce yet.
- **Sales rep** — may fill the form on a buyer's behalf; uses the Internal Use section.
- **Admin / order processing** — receives the PDF, processes payment and fulfillment.

## 4. Key flow

1. Buyer opens the site and selects a **collection / season** code (e.g. Fall 2026 / F26).
2. The product table loads live from Salesforce (style, color, price) for that season.
3. Buyer enters **email or account ID**; the system looks up Salesforce and, on a match, auto-fills Bill To / Ship To / tax ID. If multiple matches, buyer picks from a dropdown. If none, fields are entered manually.
4. Buyer enters quantities per size; line totals, order total, and total pieces calculate automatically.
5. System validates the **order minimum**. If not met, submission is blocked with a clear message.
6. Buyer completes payment, tax-exemption, signature, terms acceptance, and (rep) Internal Use fields.
7. On **Submit**: order saved to PostgreSQL (without the card number), PDF generated and saved server-side for admin *(email delivery deferred)*, buyer sees a confirmation page.

_See `architecture.md` and `wooden-ships-order-flow.mermaid` / `.drawio` for the technical flow._

## 5. Functional requirements — form fields

The website must reproduce all fields from the Excel form. Fields marked _auto_ are populated by Salesforce or computed.

### 5.1 Order header
- Collection / season selector (drives product list)
- Order date
- Order total $$ _(auto)_
- Ship window note (informational: "allow 7–12 days for transit")
- Part ship OK? (Yes / No)

### 5.2 Buyer lookup (new — enables autofill)
- Email or account ID (lookup key)
- Matching-account dropdown (when >1 candidate)

### 5.3 Bill To
- Buyer name, Street, City / State, Zip, Tel, Fax

### 5.4 Ship To
- Email (required), Street, City / State, Zip, Resale tax ID

### 5.5 Products (line items) — from Salesforce
Per row: Code #, Style name, Color, X/S qty, S/M qty, M/L qty, Total qty _(auto)_, Unit price $ _(from Salesforce)_, Line total $ _(auto)_. Plus grand total _(auto)_.

> Decision 2026-07-14: these 3 sizes are the only orderable ones — X/L and O/S SKUs that exist in Salesforce are excluded from the web form.

> Revision 2026-07-15 (Prada): the product table is **manual line entry**, not a full catalog listing. Each line has a style typeahead (suggestions by style name / code # from the season's catalog), a color dropdown for the chosen style, and auto-filled code/price; an "+ Add line" button appends lines and each line can be removed. Duplicate style+color lines are flagged. This mirrors the blank-lines layout of the original Excel form.

### 5.6 Payment
- Credit card number, Name as it appears on card, Exp date, Security code (CVV)

### 5.7 Tax exemption certificate (checkboxes)
- Rep has notified account that a state-issued certificate is required
- Account confirms sending certificate (orders will not process without this)
- Certificate on file _(internal)_

### 5.8 Terms & signature
- Terms & conditions text (made-to-order, adjustments, claims, restocking, final sale, DHL shipping)
- Buyer's signature, Date
- Accept terms checkbox

### 5.9 Internal Use section (visible on the form, per decision)
- New or reorder
- New account / existing
- Campaign (Rep non-show order / Other)
- PO #
- Rep
- Order written by
- Split (Y/N) with
- Certificate on file

### 5.10 Footer
- Static: website URLs + `@woodenshipsknits`

## 6. Validation rules

- **Order minimum:** 18 pieces total, 4 pieces per style, 2 pieces per SKU, no pre-packs. Additional singles allowed once a style reaches its 4-piece minimum.
  > Implemented reading (2026-07-15, confirm with Prada): a size cell with quantity 1 is rejected only while its style (across colors) has fewer than 4 pieces; once the style totals ≥ 4, singles are allowed. Authority: `backend/app/validation/order_minimum.py`.
- **Email (Ship To):** required, valid format.
- **Quantities:** non-negative integers only.
- **Terms acceptance:** required before submit.
- **Signature:** required before submit.
- Clear inline errors; the failing rows/fields are highlighted.

## 7. Security & compliance (payment)

- Per the current decision, card fields are collected on the form to mirror the Excel form.
- **The card number and CVV must NOT be persisted in PostgreSQL.** They appear only in the generated PDF for the admin to process manually, then are discarded from the application.
- All traffic over HTTPS/TLS.
- Recommended future path: replace raw card capture with a PCI-compliant gateway (e.g. Stripe) to remove PCI-DSS liability. Flagged, not required for v1.

## 8. Deliverables

- Web app (frontend + backend) deployable on the existing GCP VM.
- PostgreSQL schema + migrations.
- Salesforce integration (products + account lookup).
- PDF generation. **(Scope decision 2026-07-14: v1 stops at PDF output — the PDF is saved server-side and available for download; email delivery to admin is deferred to a follow-up.)**
- ~~Email delivery to admin / admin-configurable recipient(s)~~ — deferred (see above).

## 9. Open items to confirm

- ~~Season/collection fields~~ — **CONFIRMED 2026-07-14:** no season field exists; season is encoded in the `ProductCode` prefix (e.g. `K57` = F26; odd = Fall, even = Spring). Color/size are encoded in `Product2.Name` (`STYLE-COLOR-SIZE`). See `architecture.md` §3.2.
- ~~Wholesale price book~~ — **CONFIRMED 2026-07-14:** one active price book per season named `"<season> Wholesale"` (e.g. `F26 Wholesale`); the season selector resolves the book by name.
- ~~Season-code year formula~~ — **VERIFIED 2026-07-14:** `F26 Wholesale` contains exactly the K57-prefixed products.
- ~~X/L size~~ — **DECISION 2026-07-14:** the form keeps the 3 Excel size columns (X/S, S/M, M/L); X/L and O/S SKUs in Salesforce are not orderable via the web form.
- ~~Buyer/account fields~~ — **CONFIRMED 2026-07-14:** person-account org; lookup directly on `Account`; tax ID is `Tax_ID_Number__c`. See `architecture.md` §3.2.
- ~~Canonical email lookup field~~ — **CONFIRMED 2026-07-14:** `ContactBuyingEmail__c`.
- ~~Account-level discounts~~ — **CONFIRMED 2026-07-14:** not applied on the form; the form shows price-book prices and discounts are handled by admin during manual processing.
- Admin email recipient address(es).
- Which sizes are true SKUs for the "2 pcs per SKU" rule — the Salesforce data model supports the assumption (each style × color × size is its own `Product2` record); confirm the business rule counts SKUs the same way.
- Whether Bill To buyer name should also be validated against Salesforce.
