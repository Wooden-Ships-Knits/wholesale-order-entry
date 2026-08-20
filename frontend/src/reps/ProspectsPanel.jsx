// The Prospects tab: map on top, filtered table beneath, one shared row set.
//
// This component owns the data and the filters; <Map> and <ProspectTable> are
// both fed from `visible`, which is why clicking a chip changes the dots and
// the rows together. Splitting the filter state between them would let the two
// halves of the page disagree about what the rep is looking at.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getProspects, markProspect } from './api'
import ProspectMap from './Map'
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
  const [city, setCity] = useState(null) // { name, bounds } from a chosen city
  const [cityOnly, setCityOnly] = useState(false) // also narrow the table to it
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

  // The chips narrow what is shown; the search box does NOT. Search is a way to
  // GO somewhere on the map, the way it works in any map app — a rep looking up
  // one store does not want the other 900 to vanish from the table underneath.
  const visible = useMemo(
    () =>
      prospects.filter((p) => {
        if (filter === 'open' && p.potentialConflict) return false
        if (filter === 'women' && !p.womenswear) return false
        if (filter === 'marked' && !p.marked) return false
        return true
      }),
    [prospects, filter],
  )

  // Matches over everything loaded, not just `visible`: searching for a store
  // the current chip happens to exclude should still find it, or the box looks
  // broken. Accounts are searchable too — "where is our Naples store" is a
  // question a rep asks.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return []
    const hit = (s) => (s || '').toLowerCase().includes(q)
    const fromProspects = prospects
      .filter((p) => hit(p.storeName) || hit(p.city) || hit(p.address))
      .map((p) => ({ id: p.id, label: p.storeName, sub: p.city, kind: 'prospect', ...p }))
    const fromAccounts = accounts
      .map((a, i) => ({ ...a, id: `account:${i}` }))
      .filter((a) => hit(a.name))
      .map((a) => ({ id: a.id, label: a.name, sub: 'current stockist', kind: 'account', ...a }))
    return [...fromProspects, ...fromAccounts].slice(0, 8)
  }, [query, prospects, accounts])

  // Every town the loaded rows mention, with how many prospects sit in it and
  // the bounds needed to frame it. Derived from the data, so searching a city
  // costs nothing and works offline — no Places autocomplete, no key, no quota.
  //
  // The limit is coverage, not cost: a town with no mapped prospect is not in
  // this list. Real city search would need OSM admin_level=8 boundaries served
  // from the backend, which would also let the highlight be point-in-polygon
  // instead of the text match below.
  const cities = useMemo(() => {
    const byName = new Map()
    for (const p of prospects) {
      const name = (p.city || '').trim()
      if (!name || p.latitude == null || p.longitude == null) continue
      const key = name.toLowerCase()
      if (!byName.has(key)) byName.set(key, { name, count: 0, bounds: [] })
      const c = byName.get(key)
      c.count += 1
      c.bounds.push([p.latitude, p.longitude])
    }
    return [...byName.values()].sort((a, b) => b.count - a.count)
  }, [prospects])

  const cityMatches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (q.length < 2) return []
    return cities
      .filter((c) => c.name.toLowerCase().includes(q))
      .slice(0, 5)
      .map((c) => ({ ...c, id: `city:${c.name}`, label: c.name, kind: 'city',
                     sub: `${c.count} prospect${c.count === 1 ? '' : 's'}` }))
  }, [query, cities])

  // Cities FIRST: typing a town name usually means the town. A store match is
  // the more specific answer, so it sits below where the eye lands next.
  const options = useMemo(() => [...cityMatches, ...matches], [cityMatches, matches])

  // What Enter picks when the rep has not arrowed anywhere. Typing the NAME of
  // a place and pressing Enter should give you that place — "Tampa" means the
  // city, even though eight of our shops are also in Tampa and matched first.
  // Anything less exact leaves the first store selected, which is the right
  // default for a partial word.
  // Typing the exact NAME of a town and pressing Enter should give you the
  // town. Anything partial leaves the first option selected.
  const defaultIndex = useMemo(() => {
    const q = query.trim().toLowerCase()
    const exact = cityMatches.findIndex((c) => c.name.toLowerCase() === q)
    return exact >= 0 ? exact : 0
  }, [query, cityMatches])

  const [active, setActive] = useState(null) // null = follow defaultIndex
  const activeIndex = active == null ? defaultIndex : active
  // Reset the manual choice whenever the list changes underneath it, or the
  // highlight sticks to a row that has become something else.
  useEffect(() => setActive(null), [query])

  const onSearchKey = async (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault() // stop the caret jumping to either end of the input
      if (!options.length) return
      const step = e.key === 'ArrowDown' ? 1 : -1
      setActive((i) => {
        const from = i == null ? defaultIndex : i
        return (from + step + options.length) % options.length
      })
      return
    }
    if (e.key === 'Escape') {
      setQuery('')
        return
    }
    if (e.key !== 'Enter') return
    // Every source is local now, so there is nothing to await and no race
    // between an instant store match and a slower remote lookup.
    if (options[activeIndex]) choose(options[activeIndex])
  }

  const choose = (m) => {
    setQuery('')
    setActive(null)
    if (m.kind === 'city') {
      // Picking a town frames it and picks out our stores in it, rather than
      // dropping a pin on one address.
      setCity({ name: m.name, bounds: m.bounds })
      setFocus(null)
      return
    }
    setCity(null)
    setFocus(m)
  }

  // Stores the highlighted city contains, by the row's own `city` field.
  //
  // A TEXT match, not point-in-polygon: `city` comes from the OSM addr:city
  // tag, and Google has no free city outline to test against. So a shop
  // tagged "Ybor City" will not count as Tampa, and one tagged "Tampa" just
  // outside the line will. Good enough to steer a rep around a map; not a
  // number to quote as coverage. A real polygon would fix both — see the note
  // in Map.jsx.
  const cityRows = useMemo(() => {
    const c = city?.name?.trim().toLowerCase()
    if (!c) return []
    return prospects.filter((p) => (p.city || '').trim().toLowerCase() === c)
  }, [city, prospects])

  // Highlighting a city does not narrow the table by itself — "Only Tampa" is
  // a second, explicit click, same principle as search not filtering.
  const tableRows = useMemo(() => {
    if (!cityOnly || !city) return visible
    const c = city.name.trim().toLowerCase()
    return visible.filter((p) => (p.city || '').trim().toLowerCase() === c)
  }, [visible, cityOnly, city])

  const clearCity = () => {
    setCity(null)
    setCityOnly(false)
  }

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
        <ProspectMap
          prospects={visible}
          accounts={accounts}
          expanded={expanded}
          focus={focus}
          highlightCity={city}
        />

        {/* Sits ON the map, like any map app's search. It moves the view; it
            never changes what the table below is showing. */}
        <div className="map-search">
          <input
            type="search"
            placeholder="Find a store or town…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onSearchKey}
          />
          {/* Towns first, then stores. Both come from the loaded rows, so the
              whole list is instant and costs nothing. */}
          {options.length > 0 && (
            <ul className="map-search-results">
              {cityMatches.length > 0 && <li className="map-search-group">Towns</li>}
              {cityMatches.map((c, i) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={i === activeIndex ? 'active' : undefined}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(c)}
                  >
                    <span>◎ {c.label}</span>
                    <span className="sub">{c.sub}</span>
                  </button>
                </li>
              ))}
              {matches.length > 0 && <li className="map-search-group">Stores</li>}
              {matches.map((m, i) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className={cityMatches.length + i === activeIndex ? 'active' : undefined}
                    onMouseEnter={() => setActive(cityMatches.length + i)}
                    onClick={() => choose(m)}
                  >
                    <span>{m.label}</span>
                    {m.sub && <span className="sub">{m.sub}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {query.trim().length >= 2 && options.length === 0 && (
            <ul className="map-search-results">
              <li className="map-search-empty">Nothing found</li>
            </ul>
          )}
        </div>

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

      {city && (
        <div className="city-banner">
          <strong>{city.name}</strong>
          <span>
            {cityRows.length} prospect{cityRows.length === 1 ? '' : 's'} here
          </span>
          <button type="button" className="chip" onClick={() => setCityOnly((v) => !v)}>
            {cityOnly ? 'Show all rows' : 'Only this city'}
          </button>
          <button type="button" className="link-btn" onClick={clearCity}>
            Clear
          </button>
        </div>
      )}

      <p className="prospect-summary">
        Showing <strong>{tableRows.length}</strong>
        {counts ? ` of ${counts.total}` : ''} prospects
        {counts?.noConflict != null && filter !== 'open' ? ` · ${counts.noConflict} with no stockist nearby` : ''}
      </p>

      <ProspectTable
        rows={tableRows}
        onFocus={setFocus}
        onToggleMark={toggleMark}
        busyId={busyId}
      />

    </>
  )
}
