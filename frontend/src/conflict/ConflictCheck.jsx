import { useEffect, useRef, useState } from 'react'
import { loadGoogleMaps } from '../lib/googleMaps'
import { seasonFromOrderName } from '../lib/season'
import { getConflictEmail } from '../admin/api'
import EmailDraftModal from '../components/EmailDraftModal'

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY

async function fetchNearby({ lat, lng, k, maxMinutes }) {
  const params = new URLSearchParams({ lat, lng, k, maxMinutes })
  const res = await fetch(`/api/accounts/nearby?${params}`)
  if (!res.ok) throw new Error(`Check failed (HTTP ${res.status})`)
  return res.json()
}

// `embedded` drops the standalone brand header — used when the tool is shown
// as a tab inside the admin app, which has its own header.
export default function ConflictCheck({ embedded = false }) {
  const inputRef = useRef(null)
  const [status, setStatus] = useState('')
  const [place, setPlace] = useState(null) // { label, lat, lng }
  const [k, setK] = useState(5)
  const [maxMinutes, setMaxMinutes] = useState(20)
  const [checking, setChecking] = useState(false)
  const [result, setResult] = useState(null)
  const [draft, setDraft] = useState(null)
  const [drafting, setDrafting] = useState(false)

  // No order exists here, so the draft is built from the searched location.
  // Coords let the backend list the conflicting stockists; the store name and
  // rep are unknown here, so the user fills them into the draft in the popup.
  async function draftEmail() {
    setDrafting(true)
    try {
      setDraft(
        await getConflictEmail({
          address: place?.label,
          lat: place?.lat,
          lng: place?.lng,
          maxMinutes,
        }),
      )
    } catch (err) {
      setStatus(err.message)
    } finally {
      setDrafting(false)
    }
  }

  // Attach Places autocomplete once.
  useEffect(() => {
    if (!API_KEY) {
      setStatus('Missing VITE_GOOGLE_MAPS_API_KEY in frontend/.env')
      return
    }
    let cancelled = false
    loadGoogleMaps(API_KEY)
      .then((maps) => {
        if (cancelled || !inputRef.current) return
        const autocomplete = new maps.places.Autocomplete(inputRef.current, {
          fields: ['formatted_address', 'geometry'],
        })
        autocomplete.addListener('place_changed', () => {
          const p = autocomplete.getPlace()
          if (!p.geometry) {
            setStatus('No details for that place — pick a suggestion from the list.')
            return
          }
          setStatus('')
          setPlace({
            label: p.formatted_address || inputRef.current.value,
            lat: p.geometry.location.lat(),
            lng: p.geometry.location.lng(),
          })
        })
      })
      .catch((e) => !cancelled && setStatus(e.message))
    return () => {
      cancelled = true
    }
  }, [])

  // Run (and re-run) the check whenever the location or settings change.
  useEffect(() => {
    if (!place) return
    let stale = false
    setChecking(true)
    fetchNearby({ lat: place.lat, lng: place.lng, k, maxMinutes })
      .then((r) => !stale && setResult(r))
      .catch((e) => !stale && setStatus(e.message))
      .finally(() => !stale && setChecking(false))
    return () => {
      stale = true
    }
  }, [place, k, maxMinutes])

  return (
    <div className="order-form conflict-page">
      {!embedded && (
        <div className="brand">
          <h1>WOODEN SHIPS</h1>
          <div className="subtitle">Store Conflict Check — internal tool</div>
        </div>
      )}

      <section className="section">
        <h2>New store location</h2>
        <div className="conflict-controls">
          <label className="grow">
            Search a location
            <input
              ref={inputRef}
              className="map-search"
              placeholder="Type the new store's address or city…"
            />
          </label>
          <label>
            Threshold (min drive)
            <input
              type="number"
              min="1"
              max="240"
              value={maxMinutes}
              onChange={(e) => setMaxMinutes(Math.max(1, Math.min(240, Number(e.target.value) || 20)))}
            />
          </label>
          <label>
            Show nearest
            <select value={k} onChange={(e) => setK(Number(e.target.value))}>
              {[5, 10, 25].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
        {status && <p className="error-banner">{status}</p>}
        {place && (
          <p className="muted checked-place">
            Checking: <strong>{place.label}</strong>
          </p>
        )}
      </section>

      {checking && <p className="muted">Checking…</p>}

      {result && !checking && (
        <section className="section">
          <div className={result.conflict ? 'verdict verdict-conflict' : 'verdict verdict-clear'}>
            {result.conflict
              ? `CONFLICT — an existing store is within ${result.maxMinutes} minutes`
              : `NO CONFLICT — nothing within ${result.maxMinutes} minutes`}
          </div>
          <div className="conflict-actions">
            {result.conflict && (
              <button type="button" onClick={draftEmail} disabled={drafting}>
                {drafting ? 'Drafting…' : 'Generate email'}
              </button>
            )}
          </div>
          {result.mode === 'straight-line' && (
            <p className="mode-note">
              Approximate result: drive times are unavailable (no Google server key), so this uses
              straight-line distance ({result.maxMinutes} min ≈ {result.maxMinutes * 0.5} miles).
            </p>
          )}
          <h2>Nearest existing stores</h2>
          <table className="neighbors">
            <thead>
              <tr>
                <th>Store</th>
                <th>Location</th>
                <th>Season</th>
                <th className="num">Miles</th>
                <th className="num">Drive (min)</th>
              </tr>
            </thead>
            <tbody>
              {result.neighbors.map((n) => (
                <tr
                  key={n.accountId}
                  className={
                    n.driveMinutes != null
                      ? n.driveMinutes < result.maxMinutes
                        ? 'row-conflict'
                        : ''
                      : n.distanceMiles < result.maxMinutes * 0.5 && result.mode === 'straight-line'
                        ? 'row-conflict'
                        : ''
                  }
                >
                  <td>{n.name}</td>
                  <td>{n.cityState}</td>
                  <td>{seasonFromOrderName(n.lastOrderName)}</td>
                  <td className="num">{n.distanceMiles}</td>
                  <td className="num">{n.driveMinutes ?? '—'}</td>
                </tr>
              ))}
              {result.neighbors.length === 0 && (
                <tr>
                  <td colSpan="5">No geocoded wholesale accounts found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {draft && <EmailDraftModal draft={draft} onClose={() => setDraft(null)} />}
    </div>
  )
}
