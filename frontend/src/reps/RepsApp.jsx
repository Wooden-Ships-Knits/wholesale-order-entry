import { useCallback, useEffect, useState } from 'react'
import { getOrders, getSession, logout } from './api'
import RepLogin from './RepLogin'
import RepMetrics from './RepMetrics'
import RepOrderTable from './RepOrderTable'

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
  const [orders, setOrders] = useState([])
  const [counts, setCounts] = useState(null)
  const [filter, setFilter] = useState('')
  const [notice, setNotice] = useState('') // server-side explanation, e.g. name not in the sheet
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
        {/* No row count here: the Total orders card above already carries the
            book size, and the active chip is what says the table is narrowed. */}
        <button type="button" className="link-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="admin-error">{error}</p>}
      {/* Why the table is empty when it is empty for a reason the rep can act
          on — without it, "your name isn't in the contact sheet" is
          indistinguishable from "you have no orders". */}
      {notice && <p className="admin-error">{notice}</p>}

      <RepOrderTable orders={orders} />
    </main>
  )
}
