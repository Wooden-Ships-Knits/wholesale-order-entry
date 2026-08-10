// "Export to Excel" for the order-monitoring table.
//
// The admin endpoint already returns the whole page of orders (<= 500) and the
// column filters run in the browser, so the export needs no backend call: it
// writes the rows the table is showing, straight from the same array the table
// renders. What is on screen is what lands in the file.
//
// Cell text is derived here rather than scraped from the DOM, so the file keeps
// its data when a cell renders as a button or a coloured chip. Where a cell's
// meaning is shared with the column filters (new account, signed) this reuses
// filterOrders' helpers — deriving either of them twice is how an export starts
// disagreeing with the filter that produced its rows.

import { isNewAccount, isSigned, rankCode } from './filterOrders'

// Column headers and widths, in the table's own order. Widths are Excel
// character units — eyeballed so the sheet opens readable without the reviewer
// having to autofit sixteen columns by hand.
const COLUMNS = [
  { header: 'Date', width: 20 },
  { header: 'Order ID', width: 12 },
  { header: 'Signature', width: 34 },
  { header: 'Season', width: 9 },
  { header: 'QTY', width: 8 },
  { header: 'Total Amount', width: 14 },
  { header: 'Ship Window', width: 16 },
  { header: 'Account Name', width: 30 },
  { header: 'Written By', width: 18 },
  { header: 'Sales Territory', width: 18 },
  { header: 'New account', width: 24 },
  { header: 'Rank', width: 7 },
  { header: 'Potential conflict', width: 40 },
  { header: 'Tax certificate', width: 14 },
  { header: 'Payment', width: 36 },
  { header: 'Notes', width: 40 },
  { header: 'Special Instruction', width: 40 },
  { header: 'Decision', width: 24 },
]

// Excel number format for the Date column. Month name rather than 7/31 for the
// same reason the table uses one — the Jakarta and US teams read a numeric date
// in opposite orders.
const DATE_FORMAT = 'mmm d, yyyy h:mm AM/PM'

/** An ISO timestamp as a Date whose UTC clock reads the *local* time.
 *
 *  An Excel serial carries no timezone — the writer encodes the Date's UTC
 *  fields — but everything else here is local: the Date column renders with
 *  toLocaleString and the date filter matches local days (filterOrders'
 *  toDayString). Handing the raw Date over would file an order placed at 21:30
 *  local under the previous day for anyone east of UTC, so the exported row
 *  would contradict both the row it came from and the date range used to
 *  select it. Shifting by the offset makes the serial say what the screen says.
 */
export function excelLocalDate(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
}

// "Aug 5" — the short form the Signature cell shows next to a signature.
function shortDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** A text cell, or an empty cell when there is nothing to say.
 *
 *  `type: String` is not decoration: order ids are hex, so a short id like
 *  "20250814" would otherwise be read as a number and lose its leading zeros. */
const text = (value) => (value ? { value: String(value), type: String } : null)

/** A numeric cell, or an empty one when the value is absent.
 *
 *  A real number rather than text, so the column sorts numerically and Excel's
 *  SUM works on it — the whole reason to want quantities in a spreadsheet.
 *  Zero is a legitimate quantity, so this checks for null/undefined explicitly
 *  rather than falsiness. */
const number = (value) =>
  value == null || Number.isNaN(Number(value)) ? null : { value: Number(value), type: Number }

/** A money cell: a real number wearing a currency format.
 *
 *  Not text like "$1,800.00" — the column has to SUM, which is most of the
 *  reason anyone exports this. Excel does the formatting. */
const MONEY_FORMAT = '"$"#,##0.00'
const money = (value) => {
  const cell = number(value)
  return cell && { ...cell, format: MONEY_FORMAT }
}

// Joined with " · " so a single cell can carry what the table stacks vertically
// (method + card summary, Yes + how it was resolved) and still read as one line.
const join = (...parts) => parts.filter(Boolean).join(' · ')

/** Signature column.
 *
 *  Three states, as in the table. The "no signature needed" case is deliberately
 *  NOT left blank here: the table can afford an empty green cell because the
 *  colour carries the meaning, but in a spreadsheet an empty cell reads as
 *  missing data rather than "not applicable". */
export function signatureText(o) {
  if (!o.signatureRequested) return 'Not required — signed on the form'

  if (o.signatureSignedAt) {
    // The buyer may have changed quantities before signing; say so, or the
    // rep's copy and the accepted order silently disagree.
    const edited =
      o.origTotalQty != null &&
      (o.origTotalQty !== o.totalQty || o.origTotalAmount !== o.totalAmount)
    return join(
      'Signed',
      o.signatureName,
      shortDate(o.signatureSignedAt),
      edited ? `edited: ${o.origTotalQty} → ${o.totalQty} pcs` : '',
    )
  }

  // Requested but unsigned. A token that exists without a sent email means the
  // send failed at submit — the reviewer has to send it by hand, so don't let
  // that read the same as "waiting on the buyer".
  return join(
    o.signatureEmailSent ? 'Awaiting signature — email sent' : 'Awaiting signature — NOT sent',
    o.signatureEmail,
  )
}

/** New account column. `isNewAccount` is the shared derivation; this only adds
 *  what the cell says beside the Yes. */
export function newAccountText(o) {
  if (o.sfAccountCreated) return 'Yes — created in Salesforce'
  if (!isNewAccount(o)) return 'No'
  // accountExists null = the Salesforce lookup didn't run or failed, so the Yes
  // is the buyer's own answer. An unverified guess must not read as a verdict.
  return o.accountExists == null ? 'Yes (unverified)' : 'Yes'
}

/** Potential-conflict column, including how the inquiry ended. */
export function conflictText(o) {
  if (!o.hasConflict) return 'No'
  if (o.conflictResolution) {
    const outcome = o.conflictResolution === 'cleared' ? 'cleared' : 'real conflict'
    return join(`Yes — resolved: ${outcome}`, o.conflictResolutionNote)
  }
  if (!o.conflictEmailSent) return 'Yes — email not sent'

  // Sent and waiting. An AI suggestion is a proposal off a captured reply, not
  // an outcome, so it is labelled as one.
  const ai =
    o.conflictAiOutcome && o.conflictAiOutcome !== 'unclear'
      ? `AI suggests: ${o.conflictAiOutcome === 'cleared' ? 'cleared' : 'real conflict'}` +
        (o.conflictAiConfidence != null ? ` (${Math.round(o.conflictAiConfidence * 100)}%)` : '')
      : ''
  return join('Yes — email sent, awaiting reply', ai)
}

/** Payment column. Never the card number — that exists only inside the
 *  encrypted admin PDF and is not in this response at all. */
export function paymentText(o) {
  if (!o.paymentMethod) return ''
  const isCard = o.paymentMethod === 'Credit Card'
  return join(
    o.paymentMethod,
    isCard && o.cardLast4 ? `•••• ${o.cardLast4}` : '',
    isCard && o.cardExp ? `exp ${o.cardExp}` : '',
    isCard ? o.cardName : '',
    o.approvalBeforeCharge === true ? 'approval first' : '',
  )
}

/** Decision column: the status, plus what it produced. */
export function decisionText(o) {
  if (o.status === 'submitted') return 'awaiting review'
  return join(o.status, o.sfOrderNumber, o.status === 'declined' ? o.statusReason : '')
}

/** Tax-certificate column. Keyed on the buyer's own `isNewAccount` answer, as
 *  the table's cell is — an established account is not chased for a cert. */
function certificateText(o) {
  if (o.hasCertificate) return 'Yes'
  return o.isNewAccount ? 'No' : 'N/A'
}

/** The orders as sheet data: one header row, then one row per order.
 *
 *  Pure and free of the xlsx writer, so it can be exercised without a browser. */
export function orderSheetData(orders) {
  const header = COLUMNS.map((c) => ({
    value: c.header,
    type: String,
    fontWeight: 'bold',
    backgroundColor: '#f1f0ec',
  }))

  const rows = orders.map((o) => {
    // A real date cell, not a string, so Excel can sort and filter the column.
    // Null for a missing or unparseable timestamp — an "Invalid Date" cell
    // makes the writer throw and takes the whole export down with it.
    const created = o.createdAt ? excelLocalDate(o.createdAt) : null

    return [
      created ? { value: created, type: Date, format: DATE_FORMAT } : null,
      text(o.shortId),
      text(signatureText(o)),
      text(o.seasonCode),
      // Total pieces as the order stands. A buyer who changed quantities at
      // signing changed this too — the Signature column carries the before/after.
      number(o.totalQty),
      money(o.totalAmount),
      text(o.shipWindow),
      text(o.accountName),
      text(o.orderWrittenBy),
      text(o.salesTerritory),
      text(newAccountText(o)),
      text(rankCode(o.rank)),
      text(conflictText(o)),
      text(certificateText(o)),
      text(paymentText(o)),
      text(o.notes),
      text(o.specialInstructions),
      text(decisionText(o)),
    ]
  })

  return [header, ...rows]
}

/** 'wooden-ships-orders-2026-08-08.xlsx' — dated, so successive exports don't
 *  overwrite each other in the Downloads folder. */
export function exportFileName(now = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `wooden-ships-orders-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.xlsx`
}

/** Build the .xlsx and hand it to the browser's downloader.
 *
 *  The writer is imported on demand: /admin shares one bundle with the buyer's
 *  order form (single Vite entry — see main.jsx), and there is no reason for
 *  every buyer to download an Excel writer they will never run. */
export async function exportOrdersXlsx(orders) {
  const { default: writeXlsxFile } = await import('write-excel-file/browser')
  await writeXlsxFile(orderSheetData(orders), {
    sheet: 'Orders',
    columns: COLUMNS.map((c) => ({ width: c.width })),
    // Freeze the header; the table is sixteen columns wide and the reviewer is
    // going to scroll.
    stickyRowsCount: 1,
  }).toFile(exportFileName())
}

// Exported for the sanity check in tools/, and so a future column change has one
// obvious place to stay in sync with the table's <thead>.
export { COLUMNS }
