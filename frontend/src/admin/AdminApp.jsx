import { useCallback, useEffect, useMemo, useState } from 'react'
import { getOrders, getSession, logout, pollReplies } from './api'
import { exportOrdersXlsx } from './exportOrders'
import { EMPTY_FILTERS, filterOrders, hasActiveFilters } from './filterOrders'
import Login from './Login'
import OrderTable from './OrderTable'
import ConflictCheck from '../conflict/ConflictCheck.jsx'
import OrderReport from './OrderReport'
import PaymentNotice from './PaymentNotice'
import CatalogPanel from './CatalogPanel'
import VersionPanel from './VersionPanel'

const TABS = [
  { value: 'orders', label: 'Orders' },
  { value: 'conflict', label: 'Conflict check' },
  { value: 'reports', label: 'Reports' },
  { value: 'notice', label: 'Payment notice' },
  { value: 'catalog', label: 'Catalog' },
  // Last, and it stays last: it is the only tab nobody opens to do their job.
  { value: 'version', label: 'Version' },
]

const FILTERS = [
  { value: 'submitted', label: 'Awaiting review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'declined', label: 'Declined' },
  { value: '', label: 'All' },
]

export default function AdminApp() {
  const [authed, setAuthed] = useState(null) // null = still checking
  const [tab, setTab] = useState('orders')
  const [orders, setOrders] = useState([])
  const [filter, setFilter] = useState('submitted')
  // Per-column filters, one object rather than one useState per column so that
  // "Clear" is a single assignment and the whole set is easy to hand around.
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [polling, setPolling] = useState(false)
  const [pollMsg, setPollMsg] = useState('')
  const [exporting, setExporting] = useState(false)

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
    } catch (err) {
      if (err.status === 401) setAuthed(false)
      else setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => {
    getSession()
      .then((d) => setAuthed(d.authenticated))
      .catch(() => setAuthed(false))
  }, [])

  useEffect(() => {
    if (authed) load()
  }, [authed, load])

  // Manually run the inbound-reply capture + classifier, then refresh so any
  // new AI suggestions show up. (Until a scheduler runs this on a cadence.)
  async function checkReplies() {
    setPolling(true)
    setPollMsg('')
    setError('')
    try {
      const r = await pollReplies()
      setPollMsg(`Captured ${r.captured}, ${r.suggested} new suggestion(s).`)
      await load()
    } catch (err) {
      if (err.status === 401) setAuthed(false)
      else setError(err.message)
    } finally {
      setPolling(false)
    }
  }

  // Download the visible rows as .xlsx. Exports `visibleOrders`, not `orders`,
  // so the file matches the table exactly — status chips and column filters
  // included. Nothing is sent to the server; the rows are already here.
  async function exportXlsx() {
    setExporting(true)
    setError('')
    try {
      await exportOrdersXlsx(visibleOrders)
    } catch (err) {
      setError(`Export failed: ${err.message}`)
    } finally {
      setExporting(false)
    }
  }

  if (authed === null) return <p className="admin-empty">Loading…</p>
  if (!authed) return <Login onSignedIn={() => setAuthed(true)} />

  return (
    <main className="admin">
      <header className="admin-head">
        <div>
          <h1>Order monitoring</h1>
          <div className="subtitle">Wooden Ships — admin</div>
        </div>
        <button
          type="button"
          className="link-btn"
          onClick={async () => {
            await logout()
            setAuthed(false)
          }}
        >
          Sign out
        </button>
      </header>

      <div className="admin-tabs">
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            className={tab === t.value ? 'admin-tab active' : 'admin-tab'}
            onClick={() => setTab(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'conflict' ? (
        <ConflictCheck embedded />
      ) : tab === 'reports' ? (
        <OrderReport />
      ) : tab === 'notice' ? (
        <PaymentNotice />
      ) : tab === 'catalog' ? (
        <CatalogPanel />
      ) : tab === 'version' ? (
        <VersionPanel />
      ) : (
        <>
          <div className="admin-toolbar">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                className={filter === f.value ? 'chip active' : 'chip'}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
            {/* Row count + reset, so an active filter can never be mistaken
                for "there are no more orders". */}
            <span className="filter-count">
              {filtered ? `${visibleOrders.length} of ${orders.length}` : orders.length} orders
            </span>
            {filtered && (
              <button type="button" className="chip" onClick={() => setFilters(EMPTY_FILTERS)}>
                Clear filters
              </button>
            )}
            <button type="button" className="link-btn" onClick={load} disabled={loading}>
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
            <button
              type="button"
              className="link-btn"
              onClick={checkReplies}
              disabled={polling}
              title="Capture new conflict replies and run the AI classifier"
            >
              {polling ? 'Checking…' : 'Check replies'}
            </button>
            {/* Exports exactly what the table is showing — say so in the
                tooltip, because the button sits next to the filters that
                decide it. */}
            <button
              type="button"
              className="link-btn"
              onClick={exportXlsx}
              disabled={exporting || !visibleOrders.length}
              title={
                visibleOrders.length
                  ? `Download ${visibleOrders.length} order${
                      visibleOrders.length === 1 ? '' : 's'
                    } as an Excel file`
                  : 'Nothing to export'
              }
            >
              {exporting ? 'Exporting…' : 'Export to Excel'}
            </button>
            {pollMsg && <span className="poll-msg">{pollMsg}</span>}
          </div>

          {error && <p className="admin-error">{error}</p>}

          <OrderTable
            orders={visibleOrders}
            allOrders={orders}
            filters={filters}
            onFilterChange={setField}
            onChanged={load}
            onError={setError}
          />

        </>
      )}
    </main>
  )
}
