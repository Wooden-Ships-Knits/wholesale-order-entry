import { useCallback, useEffect, useState } from 'react'
import { getOrders, getSession, logout } from './api'
import Login from './Login'
import OrderTable from './OrderTable'

const FILTERS = [
  { value: 'submitted', label: 'Awaiting review' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'declined', label: 'Declined' },
  { value: '', label: 'All' },
]

export default function AdminApp() {
  const [authed, setAuthed] = useState(null) // null = still checking
  const [orders, setOrders] = useState([])
  const [filter, setFilter] = useState('submitted')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

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
        <button type="button" className="link-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="admin-error">{error}</p>}

      <OrderTable orders={orders} onChanged={load} onError={setError} />
    </main>
  )
}
