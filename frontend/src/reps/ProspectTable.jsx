// Prospect rows beneath the map, with a per-column filter row and sortable
// headers. Read-only apart from the "mark" toggle, which is the rep's own
// shortlist and the only thing on this page they can change.
//
// Written separately from RepOrderTable for the same reason that one was split
// from admin's OrderTable: shared table components accrete columns that only
// one caller may show, and this page must never be able to render an order's
// dollar value or card state by accident.

import { useState } from 'react'

import { VERDICTS } from './filterProspects'

const DASH = <span className="unknown">—</span>

// Colour per verdict. The LABELS live in filterProspects.VERDICTS so the
// filter dropdown and the badge below can never disagree about what a value
// is called.
const VERDICT_CLASS = {
  strong: 'verdict-strong',
  possible: 'verdict-possible',
  weak: 'verdict-weak',
  insufficient_data: 'verdict-unknown',
}

/** A header that sorts. Clicking cycles asc → desc → off, so a rep can always
 *  get back to the server's own order without reloading. The arrow shows the
 *  CURRENT direction rather than what a click would do — an arrow meaning
 *  "what happens next" reads backwards to most people. */
function SortHeader({ label, sortKey, sort, onSort }) {
  const active = sort.key === sortKey
  const arrow = !active ? '↕' : sort.dir === 'asc' ? '↑' : '↓'
  return (
    <th>
      <button
        type="button"
        className={active ? 'sort-btn active' : 'sort-btn'}
        onClick={() => onSort(sortKey)}
        title={`Sort by ${label.toLowerCase()}`}
      >
        {label} <span className="sort-arrow">{arrow}</span>
      </button>
    </th>
  )
}

const VISIBLE_BRANDS = 3

/** The shelf a shop stocks, DEEPEST-STOCKED FIRST and never re-sorted: the
 *  order is the evidence, since a shop whose leading brand is its own name is
 *  exactly the one a rep must not spend a call on.
 *
 *  The rest are behind a toggle rather than a `title` tooltip. A tooltip never
 *  appears on a touch screen, cannot be selected or copied, and vanishes while
 *  you read it — so the list it held was, in practice, unreachable. A real
 *  <button> so it is reachable by keyboard too, styled as the hint text it
 *  replaces because a cell full of buttons reads as a form. */
function BrandList({ brands }) {
  const [open, setOpen] = useState(false)
  if (!brands) {
    // NOT "none": the shop fills no vendor field on any product, which is a
    // different fact from stocking nothing — and it is why the assessment
    // beside this reads insufficient_data.
    return <span className="unknown">no brands recorded</span>
  }
  const hidden = brands.length - VISIBLE_BRANDS
  return (
    <div className="cert-missing">
      <span>{(open ? brands : brands.slice(0, VISIBLE_BRANDS)).join(', ')}</span>
      {hidden > 0 && (
        <button
          type="button"
          className="brand-more"
          aria-expanded={open}
          onClick={(e) => {
            e.stopPropagation() // the whole row flies the map; this must not
            setOpen(!open)
          }}
        >
          {open ? 'show fewer' : `+${hidden} more`}
        </button>
      )}
    </div>
  )
}

export default function ProspectTable({
  rows,
  allRows, // unfiltered, so the dropdowns don't shrink as you filter
  filters,
  onFilterChange,
  sort,
  onSort,
  onFocus,
  onToggleMark,
  busyId,
}) {
  return (
    <table className="admin-table prospect-table">
      <thead>
        <tr>
          <th aria-label="Shortlist" />
          <SortHeader label="Store" sortKey="storeName" sort={sort} onSort={onSort} />
          <SortHeader label="Where" sortKey="city" sort={sort} onSort={onSort} />
          <th>Contact</th>
          <SortHeader label="Assessment" sortKey="verdict" sort={sort} onSort={onSort} />
          {/* Sits beside the assessment because it is the evidence behind it:
              a shop whose leading brand is its own name is the one a rep must
              not spend a call on. */}
          <th>Brands</th>
          <SortHeader
            label="Nearest stockist"
            sortKey="distanceMiles"
            sort={sort}
            onSort={onSort}
          />
        </tr>
        {/* Per-column filters. Every cell is bound to one key of the `filters`
            object owned by ProspectsPanel; '' means "no filter on this
            column". SIX cells for six header columns — a short row silently
            shifts every control one column left. */}
        <tr className="filter-row">
          <th aria-hidden="true" />
          <th>
            <input
              type="search"
              placeholder="Store name"
              aria-label="Filter by store name"
              value={filters.storeName}
              onChange={(e) => onFilterChange('storeName', e.target.value)}
            />
          </th>
          <th>
            {/* Free text, not a dropdown: a state-wide sweep produces hundreds
                of towns, and scrolling a list that long to find one is slower
                than typing three letters of it. Matches the address too, so a
                street or postcode narrows it as well. */}
            <input
              type="search"
              placeholder="Town or address"
              aria-label="Filter by town or address"
              value={filters.city}
              onChange={(e) => onFilterChange('city', e.target.value)}
            />
          </th>
          {/* No Contact filter: "has a website" is already how the enrichment
              step is targeted, and nobody browses this table by it. The cell
              stays so the six filter cells keep lining up with six columns. */}
          <th aria-hidden="true" />
          <th>
            {/* "Not assessed" is a real choice, not the absence of one — it is
                the pile a rep works through, and blank already means "all". */}
            <select
              aria-label="Filter by assessment"
              value={filters.verdict}
              onChange={(e) => onFilterChange('verdict', e.target.value)}
            >
              <option value="">All</option>
              {Object.entries(VERDICTS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
              <option value="none">Not assessed</option>
            </select>
          </th>
          <th aria-hidden="true" />
          <th aria-hidden="true" />
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td className="admin-empty-row" colSpan={7}>
              No prospects match these filters.
            </td>
          </tr>
        )}
        {rows.map((p) => (
          // The whole row is the map control: clicking anywhere flies to the
          // store, so a rep reading the list never has to hunt for its dot.
          <tr
            key={p.id}
            className={p.potentialConflict ? 'row-conflict' : undefined}
            onClick={() => onFocus(p)}
          >
            <td>
              <button
                type="button"
                className={p.marked ? 'mark-btn marked' : 'mark-btn'}
                disabled={busyId === p.id}
                title={p.marked ? 'Remove from your shortlist' : 'Add to your shortlist'}
                onClick={(e) => {
                  e.stopPropagation() // don't also fly the map
                  onToggleMark(p)
                }}
              >
                {p.marked ? '★' : '☆'}
              </button>
            </td>
            <td>
              <div className="cert-missing">
                <span>{p.storeName}</span>
                {/* Only shown when OSM positively said so — an absent tag is
                    not evidence either way, so there is no "no" badge. */}
                {p.womenswear && <span className="sub badge-women">womenswear</span>}
              </div>
            </td>
            <td>
              <div className="cert-missing">
                <span>{p.city || DASH}</span>
                {p.address && <span className="sub">{p.address}</span>}
              </div>
            </td>
            <td>
              <div className="cert-missing">
                {p.website ? (
                  <a
                    href={p.website}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    website
                  </a>
                ) : (
                  DASH
                )}
                {p.phone && <span className="sub">{p.phone}</span>}
                {/* mailto rather than plain text: a rep reading this on a
                    phone should be one tap from writing to them. */}
                {p.email && (
                  <a
                    className="sub"
                    href={`mailto:${p.email}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {p.email}
                  </a>
                )}
              </div>
            </td>
            {/* Never blank when a row HAS been assessed and never a verdict
                when it has not: "not looked at yet" and "looked at and weak"
                are different answers, and a rep planning a week needs to tell
                them apart. */}
            <td>
              {p.verdict ? (
                <div className="cert-missing">
                  <span className={VERDICT_CLASS[p.verdict]}>
                    {VERDICTS[p.verdict] || p.verdict}
                  </span>
                  {/* The sentence written for exactly this decision. Truncated
                      by CSS, not by JS — the full text is the title. */}
                  {p.forTheRep ? (
                    <span className="sub verdict-note" title={p.forTheRep}>
                      {p.forTheRep}
                    </span>
                  ) : p.reasons ? (
                    /* A GATED row has no sentence written for a rep: the gates
                       in assess.py answer before any model call, so
                       `_unreadable` sets for_the_rep to "" and puts the finding
                       in `reasons`. 196 of 226 insufficient_data rows rendered
                       an empty cell because of it — the one verdict whose whole
                       job is to say "we could not read this shop" said nothing
                       at all, which reads as a broken page rather than an
                       answer. */
                    <span className="sub verdict-note" title={p.reasons}>
                      {p.reasons}
                    </span>
                  ) : null}
                  {/* The number rule 3 turns on. Shown because a shop can be
                      worth calling while its median price sits above our band —
                      without this the verdict reads as arbitrary. */}
                  {p.knitInBandShare != null && (
                    <span
                      className="sub"
                      title="Share of this shop's knitwear already priced inside our $100–200 band"
                    >
                      {Math.round(p.knitInBandShare * 100)}% of its knitwear in our price band
                    </span>
                  )}
                  {/* judge.check() disagreed with the answer above it. Shown
                      LOUDLY: this is the only thing marking the verdict beside
                      it as one nobody has checked. */}
                  {p.problems && (
                    <span className="sub verdict-problem" title={p.problems}>
                      ⚠ unchecked: {p.problems}
                    </span>
                  )}
                </div>
              ) : (
                <span className="unknown">not assessed</span>
              )}
            </td>
            {/* The shelf, DEEPEST-STOCKED FIRST — never re-sorted, because the
                order is the evidence. Three fit; the rest are counted, and the
                whole list is the title. */}
            <td>
              <BrandList brands={p.topBrands} />
            </td>
            <td>
              {p.nearestStockist ? (
                <div className="cert-missing">
                  <span>{p.nearestStockist}</span>
                  {p.distanceMiles != null && (
                    <span className="sub">
                      {p.distanceMiles} mi
                      {p.potentialConflict ? ' — within catchment' : ''}
                    </span>
                  )}
                </div>
              ) : (
                DASH
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
