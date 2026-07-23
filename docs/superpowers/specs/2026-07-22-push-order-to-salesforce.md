# Push accepted order to Salesforce (Kugamon) — design

**Status:** BUILT 2026-07-23 (trigger = Accept) · not yet run against prod · **Date:** 2026-07-22

## Built (2026-07-23)
`POST /api/admin/orders/{id}/status` with `accepted` calls `_push_order_to_salesforce`
→ `sf_client.create_sales_order(header, lines)`. Header first, then one line per
size (product + qty only; Kugamon prices from the header price book). Created
`kugo2p__SalesOrder__c` id + auto-number Name stored in `orders.sf_order_id` /
`sf_order_number` (migration 0009). **Idempotent** (skips if `sf_order_id` set);
**guards** on missing `sf_account_id` (create the account first) and missing
price book; on any SF error it raises BEFORE flipping status, so the order stays
actionable and the team can retry Accept. Confirm dialog on Accept. All header +
line fields verified createable via describe 2026-07-23; `Name`/`Status`/totals
left to Kugamon (not createable). Pricebook resolved live per season.

**Remaining (live-behaviour, resolve on first sandbox/prod create):** does Kugamon
auto-price + auto-total from the price book? Any trigger-forced fields? Known gap:
if the header succeeds but a line is rejected, an orphan Draft is left in SF
(error names the order id) — no auto-rollback in v1.


When the monitoring team clicks **Accept** on an order in `/admin`, create the
corresponding **Kugamon sales order** in Salesforce as a **Draft**. The team then
Submits / Approves / Releases it inside Salesforce as normal — we never advance
the status past Draft.

## Objects

- Header: **`kugo2p__SalesOrder__c`** (auto-numbered `Name`, e.g. `SO-260721-0073266`)
- Lines: **`kugo2p__SalesOrderProductLine__c`** (child relationship
  `kugo2p__Sales_Order_Product_Lines__r`)

## Field mapping (verified against the live org, 2026-07-22)

**Header**

| Salesforce field | Source (our order) |
|---|---|
| `kugo2p__Account__c` | `sf_account_id` |
| `kugo2p__Pricebook2Id__c` | the season's wholesale price book (already resolved) |
| `Written_By__c` | `order_written_by` (rep orders only) — **leave empty for direct/customer orders** (field is nillable; decision 2026-07-22) |
| `kugo2p__BillToName__c` | `account_name` |
| `Start_Ship_Date__c` | parse from the ship-window string (e.g. `"8/1-30"` → `2026-08-01`) |
| `kugo2p__Warehouse__c` | **`a0p900000008hZlAAI` (`000 - Bali`)** — see Warehouse below |
| `Name`, `kugo2p__Status__c`, `TotalAmount`, `Total_Units` | **do NOT set** — auto by Kugamon |

**Line** (one per size with qty > 0, using the stored per-size Product2 id)

| Salesforce field | Source |
|---|---|
| `kugo2p__SalesOrder__c` | the created header id |
| `kugo2p__Product__c` | `order_item.sf_product_id_xs / _sm / _ml` |
| `kugo2p__Quantity__c` | `order_item.qty_xs / qty_sm / qty_ml` |

> Kugamon has ~13 quantity fields on the line (shipped, invoiced, cancelled,
> etc. — all for later lifecycle stages). For a new order set only
> **`kugo2p__Quantity__c`** (the ordered qty); leave the rest to the package.

## Warehouse

**Always use `000 - Bali` (`a0p900000008hZlAAI`)** — the org default (~59k orders
vs ~4k for the next, `002 - NY`).

The real business rule is: *if any single SKU is ordered > 24 pcs, the warehouse
should be `3-[Account Name]`* (the per-store warehouses — 115 of them, named after
accounts). **We deliberately skip this** in v1:

- The order is created as a **Draft**, which the team reviews in Salesforce
  before Submit — so the rare >24/SKU case can be corrected by hand there.
- Automating it is fragile: look up `3-[Account Name]` by name → may not exist
  for every account → failure handling.

**Optional safety add (not v1):** flag orders where any SKU qty > 24 — a note on
the Draft or a marker on the admin row — so the team knows to switch that order's
warehouse manually. Automated warning, manual fix.

## Trigger to build it

`POST /api/admin/orders/{id}/status` with `accepted` already runs on Accept —
that's the hook. On success, create the SF header + lines, then store the new
`kugo2p__SalesOrder__c` id on our order row.

## Still unknown — resolve by creating ONE order in a **sandbox** (`SALESFORCE_DOMAIN=test`)

- Which fields Kugamon's triggers *force* at creation (beyond the mapping above)
- Create order: header first then lines, or together?
- Auto-pricing: does the package pull line prices from the price book, or must we
  set `ListPrice` / `SalesPrice`?
- Auto-totals: does it calculate `TotalAmount` / `Total_Units`, or do we?

Metadata understates managed-package requirements — the sandbox create is the
real spec.

## Must-haves for the build

- **Idempotency:** never create twice. Check for a stored SF order id before
  creating; skip (or no-op) if present. Accept clicked twice must not duplicate.
- **Write permission:** the integration user (`ppic@pt-infashion.com`) needs
  create rights on both objects.
- **Failure handling:** a failed SF push must not silently lose the accept.
  Suggest storing a sync state (e.g. `sf_order_id` null = not synced, plus an
  error field) so a Kugamon hiccup is visible and retryable, separate from the
  `accepted` status.
- **Sandbox first.** Creating orders is a write to the live system.
