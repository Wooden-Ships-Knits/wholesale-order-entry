import { useCallback, useEffect, useMemo, useState } from 'react'
import { getOrders, getSession, logout } from './api'
import { EMPTY_FILTERS, filterOrders, hasActiveFilters, STATUS_FILTERS } from './filterOrders'
import RepLogin from './RepLogin'
import RepMetrics from './RepMetrics'
import RepOrderTable from './RepOrderTable'

export default function RepsApp() {
  const [rep, setRep] = useState(null) // null = still checking, '' = signed out
  const [orders, setOrders] = useState([])
  const [counts, setCounts] = useState(null)
  const [filter, setFilter] = useState('')
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
          <h1>My orders</h1>
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
    </main>
  )
}
