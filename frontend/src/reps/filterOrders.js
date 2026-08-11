// Client-side column filters for the rep dashboard table.
//
// Same shape and behaviour as the admin table's filters (frontend/src/admin/
// filterOrders.js) — a rep who has seen /admin should not have to learn a
// second set of controls. The date and signature predicates are imported from
// there rather than re-written, so the two pages can never disagree about what
// "signed" or "on this day" means.
//
// Only the pure predicates are shared. The row *serializers* stay separate on
// purpose (see CLAUDE.md): admin's rows carry card, conflict, certificate and
// Salesforce fields a rep must never receive, and none of them are referenced
// here.

import { distinctValues, isSigned, toDayString } from '../admin/filterOrders'

export { distinctValues, isSigned, toDayString }

// Every filter field is a string; '' always means "no filter on this column",
// so an empty set matches everything and the checks compose.
//
// Deliberately no `status` key: Decision is filtered server-side by the
// toolbar chips, and the Decision column's dropdown drives that same state.
// Two controls over one column would let them contradict each other.
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
  notes: '',
}

/** Decision / status options, shared by the toolbar chips and the Decision
 *  column dropdown so the two lists can't drift. '' (All) first, unlike
 *  /admin's "Awaiting review": the office triages a pending queue, a rep wants
 *  their whole recent book. */
export const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'submitted', label: 'Awaiting review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'declined', label: 'Declined' },
]

const contains = (value, query) => String(value ?? '').toLowerCase().includes(query)

// Tri-state ('' | 'yes' | 'no') against a possibly-null boolean.
const matchesYesNo = (choice, value) => !choice || Boolean(value) === (choice === 'yes')

export function filterOrders(orders, f) {
  // Normalise the text queries once instead of per row.
  const shortId = f.shortId.trim().toLowerCase()
  const accountName = f.accountName.trim().toLowerCase()
  const notes = f.notes.trim().toLowerCase()

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
    if (notes && !contains(o.notes, notes)) return false

    return true
  })
}

/** True when at least one column filter is active — drives the "Clear filters"
 *  button and the "no rows match" empty state. */
export const hasActiveFilters = (f) => Object.values(f).some((v) => v !== '')
