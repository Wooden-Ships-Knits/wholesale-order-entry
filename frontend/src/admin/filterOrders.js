// Client-side column filters for the order-monitoring table.
//
// The admin endpoint returns the whole page of orders at once (<= 500), so
// filtering happens in the browser — no extra round trip, instant feedback.
// If that row cap is ever raised past a few thousand, move these predicates
// into `GET /api/admin/orders` as query params; the UI shape stays the same.

// Every filter field is a string; '' always means "no filter on this column",
// so an empty set matches everything and the checks compose.
export const EMPTY_FILTERS = {
  dateFrom: '', // 'YYYY-MM-DD' straight out of <input type="date">
  dateTo: '',
  shortId: '',
  sign: '', // '' | 'yes' | 'no' — has the buyer signed?
  season: '',
  shipWindow: '',
  accountName: '',
  writtenBy: '', // Internal Use "Order written by"; '' on customer-filled orders
  territory: '',
  newAccount: '', // '' | 'yes' | 'no'
  paymentMethod: '', // '' | 'Credit Card' | 'PayPal'
  rank: '', // rank code only ('A', 'B', 'C'…)
  conflict: '', // '' | 'yes' | 'no'
  certificate: '', // '' | 'yes' | 'no'
  notes: '',
  specialInstructions: '',
}

/** Local-calendar 'YYYY-MM-DD' for an ISO timestamp.
 *  Deliberately NOT toISOString(): an order placed at 21:00 local rolls over to
 *  the next UTC day, which would make it vanish from a filter on the day the
 *  table visibly shows (the cell renders with toLocaleString). */
export function toDayString(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Leading code of a rank string ("C - $2,000+ / Monthly" -> "C"), matching
 *  what the Rank column displays. */
export function rankCode(rank) {
  return rank ? rank.split(' - ')[0].trim() : ''
}

/** Is this a new account? Shared by the New account cell and its column filter
 *  — if the two ever derive it separately they drift, and filtering "Yes" hides
 *  rows the table shows as Yes.
 *
 *  A store Salesforce doesn't have is new. accountExists null means the lookup
 *  didn't run, so fall back to what the buyer answered. */
export function isNewAccount(o) {
  if (o.sfAccountCreated) return true // we made it; the lookup now finds it
  if (o.accountExists == null) return Boolean(o.isNewAccount)
  return !o.accountExists
}


/** Does this order have the buyer's signature? Shared by the Signature cell and
 *  its column filter, for the same reason as isNewAccount above.
 *
 *  The column shows three states, not two: no signature was ever requested
 *  (the customer signed the form itself, so nothing is outstanding), signed via
 *  the emailed link, or requested and still waiting. Only the last of those is
 *  unsigned — filtering on signatureSignedAt alone would report every
 *  customer-filled order as unsigned, which is most of them. */
export function isSigned(o) {
  return !o.signatureRequested || Boolean(o.signatureSignedAt)
}


const contains = (value, query) => String(value ?? '').toLowerCase().includes(query)

// Tri-state ('' | 'yes' | 'no') against a possibly-null boolean. null/undefined
// count as No, matching how those cells render.
const matchesYesNo = (choice, value) => !choice || Boolean(value) === (choice === 'yes')

export function filterOrders(orders, f) {
  // Normalise the text queries once instead of per row.
  const shortId = f.shortId.trim().toLowerCase()
  const accountName = f.accountName.trim().toLowerCase()
  const notes = f.notes.trim().toLowerCase()
  const specialInstructions = f.specialInstructions.trim().toLowerCase()

  return orders.filter((o) => {
    if (f.dateFrom || f.dateTo) {
      // ISO day strings sort lexicographically the same way they sort
      // chronologically, so plain string compares are enough here.
      const day = toDayString(o.createdAt)
      if (!day) return false
      if (f.dateFrom && day < f.dateFrom) return false
      if (f.dateTo && day > f.dateTo) return false
    }

    // Match the full uuid too, so an id pasted from an email finds its row.
    if (shortId && !contains(o.shortId, shortId) && !contains(o.id, shortId)) return false
    if (!matchesYesNo(f.sign, isSigned(o))) return false
    if (f.season && o.seasonCode !== f.season) return false
    if (f.shipWindow && o.shipWindow !== f.shipWindow) return false
    if (accountName && !contains(o.accountName, accountName)) return false
    if (f.writtenBy && o.orderWrittenBy !== f.writtenBy) return false
    if (f.territory && o.salesTerritory !== f.territory) return false
    if (!matchesYesNo(f.newAccount, isNewAccount(o))) return false
    if (f.paymentMethod && o.paymentMethod !== f.paymentMethod) return false
    if (f.rank && rankCode(o.rank) !== f.rank) return false
    if (!matchesYesNo(f.conflict, o.hasConflict)) return false
    if (!matchesYesNo(f.certificate, o.hasCertificate)) return false
    if (notes && !contains(o.notes, notes)) return false
    if (specialInstructions && !contains(o.specialInstructions, specialInstructions)) return false

    return true
  })
}

/** True when at least one column filter is active — drives the "Clear filters"
 *  button and the "no rows match" empty state. */
export const hasActiveFilters = (f) => Object.values(f).some((v) => v !== '')

/** Sorted distinct values of one field, for the column dropdowns. Derived from
 *  the loaded rows so the options can never drift from the data. */
export function distinctValues(orders, pick) {
  return [...new Set(orders.map(pick).filter(Boolean))].sort()
}
