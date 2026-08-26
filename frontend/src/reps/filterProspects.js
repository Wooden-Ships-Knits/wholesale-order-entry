// Client-side column filters and sorting for the prospects table.
//
// Same shape as filterOrders.js next door — a rep who has learned the Orders
// table should not have to learn a second set of controls. Kept separate
// because the columns share nothing: an order has a season and a signature, a
// prospect has a town and a verdict.

import { distinctValues } from '../admin/filterOrders'

export { distinctValues }

// The four values app/prospects/assess.py can write, in the order a rep cares
// about. Exported so the table's dropdown and its badge labels come from one
// list — two copies would drift the moment a verdict is renamed.
export const VERDICTS = {
  strong: 'Strong',
  possible: 'Possible',
  weak: 'Weak',
  insufficient_data: 'Couldn’t read site',
}

// Every filter field is a string; '' always means "no filter on this column",
// so an empty set matches everything and the checks compose.
export const EMPTY_FILTERS = {
  storeName: '',
  city: '', // free text — matches the town OR the street address
  verdict: '', // '' | one of VERDICTS | 'none' for not-yet-assessed
  brands: '', // free text — matches ANY brand in topBrands
}

const has = (value, needle) =>
  (value || '').toLowerCase().includes(needle.trim().toLowerCase())

export function filterProspects(rows, f) {
  return rows.filter((p) => {
    if (f.storeName && !has(p.storeName, f.storeName)) return false
    // Town OR address: the box says "Town or address", and a rep looking for
    // a high street should not have to know which column it landed in.
    if (f.city && !(has(p.city, f.city) || has(p.address, f.city))) return false
    // 'none' is a real choice, not the absence of one: "nobody has looked at
    // this yet" is the pile a rep works through, and it cannot be expressed by
    // leaving the dropdown blank because blank means "all".
    if (f.verdict === 'none' && p.verdict) return false
    if (f.verdict && f.verdict !== 'none' && p.verdict !== f.verdict) return false
    // ANY brand, not the joined string: joining would let "free people" match a
    // shop stocking "Free" and "People Tree", which is the wrong answer to the
    // question a rep is asking. Matches partially so "madewell" finds
    // "Madewell" without anyone typing the case correctly.
    if (f.brands && !(p.topBrands || []).some((b) => has(b, f.brands))) return false
    return true
  })
}

export const hasActiveFilters = (f) => Object.values(f).some((v) => v !== '')

// Which columns can be sorted, and how each reads its value. Sorting by a
// getter rather than the raw key lets "Where" sort on the town and "Rating"
// sort numerically, without the table knowing anything about the shape.
export const SORTABLE = {
  storeName: (p) => (p.storeName || '').toLowerCase(),
  city: (p) => (p.city || '').toLowerCase(),
  rating: (p) => (p.rating == null ? null : Number(p.rating)),
  verdict: (p) => (p.verdict ? Object.keys(VERDICTS).indexOf(p.verdict) : null),
  distanceMiles: (p) => (p.distanceMiles == null ? null : Number(p.distanceMiles)),
}

/** Sorted copy. `dir` is 'asc' | 'desc'; a null key leaves the order alone.
 *
 *  BLANKS ALWAYS SINK. A shop with no rating or no verdict is missing data,
 *  not a low score — floating it to the top of an ascending sort would bury
 *  the rows the rep actually wants under the ones nobody has looked at.
 */
export function sortProspects(rows, key, dir = 'asc') {
  const get = SORTABLE[key]
  if (!get) return rows
  const sign = dir === 'desc' ? -1 : 1
  return [...rows].sort((a, b) => {
    const x = get(a)
    const y = get(b)
    const xEmpty = x === null || x === '' || x === undefined
    const yEmpty = y === null || y === '' || y === undefined
    if (xEmpty && yEmpty) return 0
    if (xEmpty) return 1 // regardless of direction
    if (yEmpty) return -1
    if (x < y) return -1 * sign
    if (x > y) return 1 * sign
    return 0
  })
}
