import { useCallback, useEffect, useMemo, useState } from 'react'
import { getOrders, getSession, logout } from './api'
import {
  EMPTY_FILTERS,
  filterOrders,
  hasActiveFilters,
  searchWithStatus,
  STATUS_FILTERS,
  statusFromSearch,
} from './filterOrders'
import ProspectsPanel from './ProspectsPanel'
import RepLogin from './RepLogin'
import RepMetrics from './RepMetrics'
import RepOrderTable from './RepOrderTable'

// Two panels and one link. An entry with `href` is NOT a tab: it navigates
// away instead of swapping the panel below, so it must never become the active
// `tab` — there is no panel to render for it, and selecting it would leave the
// Orders table showing under a heading that says otherwise.
const TABS = [
  { value: 'orders', label: 'Orders' },
  { value: 'prospects', label: 'Prospects' },
  { value: 'dof', label: 'DOF', href: '/order_form' },
]

// All first, unlike /admin's "Awaiting review": the office triages a pending
// queue, a rep wants their whole recent book.

const FILTERS = [
  { value: '', label: 'All' },
  { value: 'submitted', label: 'Awaiting review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'declined', label: 'Declined' },
]

export default function RepsApp() {
  const [rep, setRep] = useState(null) // null = still checking, '' = signed out
  const [tab, setTab] = useState('orders')
  const [orders, setOrders] = useState([])
  const [counts, setCounts] = useState(null)
  // Seeded from the URL so a link can drop a rep straight onto one queue
  // (/reps?status=submitted). Lazy initialiser: the query string is read once,
  // on mount, so from then on the chips drive the URL and not the other way
  // round. It survives sign-in because RepLogin renders in place — no
  // navigation, so the address bar is untouched while the rep types.
  const [filter, setFilter] = useState(() => statusFromSearch(window.location.search))
  // Per-column filters, one object rather than one useState per column so that
  // "Clear" is a single assignment and the whole set is easy to hand around.
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [notice, setNotice] = useState('') // server-side explanation, e.g. name not in the sheet
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const setField = (key, value) => setFilters((f) => ({ ...f, [key]: value }))

  // Derived, not state: the visible rows are always a function of (orders,
  // filters), so there is nothing to keep in sync.
  const visibleOrders = useMemo(() => filterOrders(orders, filters), [orders, filters])
  const filtered = hasActiveFilters(filters)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await getOrders(filter)
      setOrders(d.orders)
      // Whole-book counts, unaffected by `filter` — see RepMetrics.
      setCounts(d.counts)
      setNotice(d.message || '')
    } catch (err) {
      if (err.status === 401) setRep('')
      else setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  // Keep the address bar in step with the chips, so whatever a rep is looking
  // at can be copied and passed on, and so a link carrying a status we don't
  // recognise stops advertising it once we've fallen back to All. replaceState,
  // not pushState: filtering is not navigation, and Back should leave the
  // dashboard rather than unwind a trail of chip clicks.
  useEffect(() => {
    const search = searchWithStatus(window.location.search, filter)
    if (search === window.location.search) return
    const { pathname, hash } = window.location
    window.history.replaceState(null, '', `${pathname}${search}${hash}`)
  }, [filter])

  useEffect(() => {
    getSession()
      .then((d) => setRep(d.authenticated ? d.name : ''))
      .catch(() => setRep(''))
  }, [])

  useEffect(() => {
    if (rep) load()
  }, [rep, load])

  if (rep === null) return <p className="admin-empty">Loading…</p>
  if (!rep) return <RepLogin onSignedIn={(name) => setRep(name)} />

  return (
    <main className="admin">
      <header className="admin-head">
        <div>
          <h1>Reps Portal</h1>
          <div className="subtitle">Wooden Ships — {rep}</div>
        </div>
        <button
          type="button"
          className="link-btn"
          onClick={async () => {
            await logout()
            setOrders([])
            setCounts(null)
            setRep('')
          }}
        >
          Sign out
        </button>
      </header>

      {/* Same markup as /admin's tabs so the two internal pages stay one
          product — see AdminApp. */}
      <div className="admin-tabs">
        {TABS.map((t) =>
          /* A real <a>, not a button with an onClick that assigns
             window.location: it goes somewhere, so cmd-click, middle-click,
             "open in new tab" and the status bar preview all have to work.
             Never carries `active` — it is not a panel that can be current. */
          t.href ? (
            <a key={t.value} className="admin-tab" href={t.href}>
              {t.label}
            </a>
          ) : (
            <button
              key={t.value}
              type="button"
              className={tab === t.value ? 'admin-tab active' : 'admin-tab'}
              onClick={() => setTab(t.value)}
            >
              {t.label}
            </button>
          ),
        )}
      </div>

      {tab === 'prospects' ? (
        <ProspectsPanel />
      ) : (
        <>
      <RepMetrics counts={counts} />

      <div className="admin-toolbar">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            className={filter === f.value ? 'chip active' : 'chip'}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
        {/* No row count while only the chips are narrowing the table: the Total
            orders card above already carries the book size, and the active chip
            is what says the table is narrowed. A column filter has no such
            marker, so once one is on, say how many rows it left. */}
        {filtered && (
          <>
            <span className="filter-count">
              {visibleOrders.length} of {orders.length} orders
            </span>
            <button type="button" className="chip" onClick={() => setFilters(EMPTY_FILTERS)}>
              Clear filters
            </button>
          </>
        )}
        <button type="button" className="link-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="admin-error">{error}</p>}
      {/* Why the table is empty when it is empty for a reason the rep can act
          on — without it, "your name isn't in the contact sheet" is
          indistinguishable from "you have no orders". */}
      {notice && <p className="admin-error">{notice}</p>}

          <RepOrderTable
            orders={visibleOrders}
            allOrders={orders}
            filters={filters}
            onFilterChange={setField}
            statusFilter={filter}
            onStatusFilterChange={setFilter}
          />
        </>
      )}
    </main>
  )
}
