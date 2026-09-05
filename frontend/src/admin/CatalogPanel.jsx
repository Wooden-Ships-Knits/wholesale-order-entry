// The "Catalog" tab: pick a collection, then tick off the style+colors that
// should not appear on the order form.
//
// SIZES ARE NOT SHOWN AND CANNOT BE HIDDEN. One block here is one style+color,
// which is the grain the price book groups to and the grain a buyer chooses at.
// Hiding a single size would mean a style whose S/M silently isn't orderable —
// a support ticket, not a feature.
//
// A tick is saved the moment it is made (one row, one request) rather than
// collected into a Save button: the tab is most useful mid-season with two
// people looking at it, and a whole-list save would have the slower tab
// overwrite the faster one's work.
import { useEffect, useMemo, useState } from 'react'
import { getAllSeasons, getCatalog, setProductHidden } from './api'

const rowKey = (r) => `${r.styleName}|||${r.color}`

export default function CatalogPanel() {
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  // Keys with a request in flight, so a double-click can't race itself.
  const [saving, setSaving] = useState(() => new Set())

  useEffect(() => {
    // limit=0 — unlike the order form, the admin may need to tidy a season
    // that is already closed.
    getAllSeasons()
      .then((d) => setSeasons(d.seasons))
      .catch((e) => setError(`Could not load collections: ${e.message}`))
  }, [])

  async function chooseSeason(code) {
    setSeason(code)
    setRows([])
    // A search typed against last season's names means nothing here, and an
    // empty result would read as "this collection has no products".
    setQuery('')
    setError('')
    setLoading(true)
    try {
      const d = await getCatalog(code)
      setRows(d.rows)
    } catch (e) {
      setError(`Could not load products: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  async function toggle(row) {
    const key = rowKey(row)
    if (saving.has(key)) return
    const next = !row.hidden
    // Optimistic: the checkbox has to answer the click, and the server is
    // authoritative only in the sense that a failure puts the tick back.
    setRows((prev) => prev.map((r) => (rowKey(r) === key ? { ...r, hidden: next } : r)))
    setSaving((prev) => new Set(prev).add(key))
    setError('')
    try {
      await setProductHidden(season, row.styleName, row.color, next)
    } catch (e) {
      setRows((prev) => prev.map((r) => (rowKey(r) === key ? { ...r, hidden: !next } : r)))
      setError(`Could not save ${row.styleName} / ${row.color}: ${e.message}`)
    } finally {
      setSaving((prev) => {
        const s = new Set(prev)
        s.delete(key)
        return s
      })
    }
  }

  // styleName -> its colors, in the order the API returned them (already
  // sorted by style then color server-side).
  const styles = useMemo(() => {
    const map = new Map()
    for (const r of rows) {
      if (!map.has(r.styleName)) map.set(r.styleName, { styleName: r.styleName, code: r.code, colors: [] })
      map.get(r.styleName).colors.push(r)
    }
    return [...map.values()]
  }, [rows])

  // Matches the style name OR the product code, the same two things the order
  // form's own typeahead searches — someone reading off a line sheet has the
  // code, someone repeating a phone call has the name.
  const visibleStyles = useMemo(() => {
    const q = query.trim().toUpperCase()
    if (!q) return styles
    return styles.filter(
      (s) => s.styleName.toUpperCase().includes(q) || (s.code || '').toUpperCase().includes(q),
    )
  }, [styles, query])

  const hiddenCount = rows.filter((r) => r.hidden).length

  return (
    <section className="catalog-panel">
      <p className="catalog-intro">
        Tick an item to remove it from the order form's style and colour pickers for
        that collection. Nothing is changed in Salesforce, and orders already placed
        or out for signature keep their prices and totals.
      </p>

      {/* A dropdown, not chips: there is one collection per season back to 2019
          and the row of buttons grew taller than the products it was there to
          filter. Matches the order form's own collection picker. */}
      <div className="catalog-picker">
        <label>
          Collection / Season
          <select value={season} onChange={(e) => chooseSeason(e.target.value)}>
            <option value="">Select a collection…</option>
            {seasons.map((s) => (
              <option key={s.code} value={s.code}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        {/* Filters styles, not colours: 518 style/colours is ~200 styles, and
            the thing anyone arrives here knowing is which style to pull. A
            matching style keeps all of its colours, so the block you land on
            is the whole decision. */}
        <label className="catalog-search">
          Find a style
          <input
            type="search"
            value={query}
            placeholder="Style name or code…"
            disabled={!season || loading}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {season && !loading && rows.length > 0 && (
          <span className="catalog-count">
            {rows.length} style/colours · <strong>{hiddenCount} hidden</strong>
            {query.trim() && ` · ${visibleStyles.length} of ${styles.length} styles shown`}
          </span>
        )}
      </div>

      {error && <p className="admin-error">{error}</p>}

      {!season ? (
        <p className="admin-empty">Choose a collection above.</p>
      ) : loading ? (
        <p className="admin-empty">Loading products…</p>
      ) : rows.length === 0 ? (
        <p className="admin-empty">No products in this collection.</p>
      ) : (
        <>
          {visibleStyles.length === 0 && (
            <p className="admin-empty">No style matches “{query.trim()}”.</p>
          )}
          {visibleStyles.map((s) => (
            <div key={s.styleName} className="catalog-style">
              <h3>
                <span className="catalog-code">{s.code}</span> {s.styleName}
              </h3>
              <div className="catalog-colors">
                {s.colors.map((r) => {
                  const key = rowKey(r)
                  return (
                    <label
                      key={key}
                      className={r.hidden ? 'catalog-item hidden' : 'catalog-item'}
                      title={r.hidden ? 'Hidden from the order form' : 'Tick to hide'}
                    >
                      <input
                        type="checkbox"
                        checked={!!r.hidden}
                        disabled={saving.has(key)}
                        onChange={() => toggle(r)}
                      />
                      {/* Colour names run to three words ("PINK WHIM/BREAKER
                          WHITE MARL"), so this wraps and the price stays put
                          rather than being shoved through the border. */}
                      <span className="catalog-color">{r.color}</span>
                      <span className="catalog-price">
                        {r.unitPrice != null ? `$${Number(r.unitPrice).toFixed(2)}` : '—'}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          ))}
        </>
      )}
    </section>
  )
}
