// The Prospects tab: map on top, filtered table beneath, one shared row set.
//
// This component owns the data and the filters; <Map> and <ProspectTable> are
// both fed from `visible`, which is why clicking a chip changes the dots and
// the rows together. Splitting the filter state between them would let the two
// halves of the page disagree about what the rep is looking at.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { getProspects, markProspect } from './api'
import Map from './Map'
import ProspectTable from './ProspectTable'

const FILTERS = [
  { value: '', label: 'All' },
  // The default view a rep wants: somewhere we do not already have a store.
  { value: 'open', label: 'No stockist nearby' },
  { value: 'women', label: 'Womenswear' },
  { value: 'marked', label: 'My shortlist' },
]

export default function ProspectsPanel() {
  const [prospects, setProspects] = useState([])
  const [accounts, setAccounts] = useState([])
  const [counts, setCounts] = useState(null)
  const [filter, setFilter] = useState('open')
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [focus, setFocus] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const d = await getProspects()
      setProspects(d.prospects || [])
      setAccounts(d.accounts || [])
      setCounts(d.counts || null)
      setNotice(d.mocked ? 'Showing sample data — the prospects endpoint is not live yet.' : '')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Esc closes the expanded map. Bound on the document rather than the map
  // container so it works no matter what has focus.
  useEffect(() => {
    if (!expanded) return
    const onKey = (e) => e.key === 'Escape' && setExpanded(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [expanded])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return prospects.filter((p) => {
      if (filter === 'open' && p.potentialConflict) return false
      if (filter === 'women' && !p.womenswear) return false
      if (filter === 'marked' && !p.marked) return false
      if (q && !`${p.storeName} ${p.city || ''}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [prospects, filter, query, ])

  const toggleMark = async (p) => {
    setBusyId(p.id)
    // Optimistic: the star flips immediately and reverts if the write fails.
    // A shortlist toggle that waits on a round trip feels broken at this size.
    const next = !p.marked
    setProspects((rows) => rows.map((r) => (r.id === p.id ? { ...r, marked: next } : r)))
    try {
      await markProspect(p.id, next)
    } catch (err) {
      setProspects((rows) => rows.map((r) => (r.id === p.id ? { ...r, marked: !next } : r)))
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
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
        <input
          type="search"
          className="prospect-search"
          placeholder="Search store or town…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="button" className="link-btn" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="admin-error">{error}</p>}
      {notice && <p className="admin-error">{notice}</p>}

      {/* The backdrop is a SIBLING of the map card, never its parent. React
          reconciles by position in the tree, so moving <Map> inside an overlay
          would unmount and rebuild it — losing pan, zoom and any open popup,
          and paying to construct the Leaflet map again. Expanding is therefore
          a class on a card that never moves; only its CSS box changes. */}
      {expanded && (
        <div className="conflict-modal-overlay" onClick={() => setExpanded(false)} />
      )}

      <div className={expanded ? 'prospect-map-card expanded' : 'prospect-map-card'}>
        <Map prospects={visible} accounts={accounts} expanded={expanded} focus={focus} />
        <button
          type="button"
          className="prospect-map-expand"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Close' : 'Expand'}
        </button>
        <div className="prospect-map-legend">
          <span><i className="dot dot-prospect" /> prospect</span>
          <span><i className="dot dot-conflict" /> stockist within 10 mi</span>
          <span><i className="dot dot-account" /> our store</span>
        </div>
      </div>

      <p className="prospect-summary">
        Showing <strong>{visible.length}</strong>
        {counts ? ` of ${counts.total}` : ''} prospects
        {counts?.noConflict != null && filter !== 'open' ? ` · ${counts.noConflict} with no stockist nearby` : ''}
      </p>

      <ProspectTable
        rows={visible}
        onFocus={setFocus}
        onToggleMark={toggleMark}
        busyId={busyId}
      />

    </>
  )
}
