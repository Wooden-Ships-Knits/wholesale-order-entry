import { useCallback, useEffect, useState } from 'react'
import { getAllSeasons, getNoticeCards, noticeCardUrl, runNotice } from './api'

export default function PaymentNotice() {
  // Seasons come from Salesforce (one per '<season> Wholesale' price book), not
  // a hardcoded list — a new season appears here as soon as its book exists.
  // Unlike the order form we ask for all of them: cards get built for past
  // seasons long after they stop being sellable.
  const [seasons, setSeasons] = useState([])
  const [season, setSeason] = useState('')
  const [soText, setSoText] = useState('')
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState('')
  const [cards, setCards] = useState([])
  const [error, setError] = useState('')

  // One SO per line; blank lines ignored so a trailing newline is harmless.
  const soNumbers = soText
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)

  const loadCards = useCallback(async () => {
    try {
      const d = await getNoticeCards()
      setCards(d.cards || [])
    } catch {
      /* listing is a convenience — never block the page on it */
    }
  }, [])

  useEffect(() => {
    loadCards()
    getAllSeasons()
      .then((d) => {
        const list = d.seasons || []
        setSeasons(list)
        // Default to the newest, which is what the list is sorted by.
        setSeason((cur) => cur || list[0]?.code || '')
      })
      .catch((e) => setError(`Could not load seasons: ${e.message}`))
  }, [loadCards])

  async function onRun() {
    if (!soNumbers.length) return
    setRunning(true)
    setError('')
    setLog('')
    try {
      const d = await runNotice(season, soNumbers)
      setLog((d.log || []).join('\n'))
      await loadCards()
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="report-card">
      <h2>Payment Notice #5</h2>
      <p className="muted">
        Builds a card of style photos for each sales order, with the ordered colours shown.
      </p>

      <div className="notice-controls">
        <label>
          Season
          <select
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            disabled={running || !seasons.length}
          >
            {!seasons.length && <option value="">Loading seasons…</option>}
            {seasons.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="notice-so">
          SO numbers — one per line
          <textarea
            rows={4}
            value={soText}
            placeholder={'SO-260720-0073265\nSO-260716-0073255'}
            onChange={(e) => setSoText(e.target.value)}
          />
        </label>
      </div>

      <div className="report-run-row">
        <button
          type="button"
          className="report-run"
          onClick={onRun}
          disabled={running || !season || !soNumbers.length}
        >
          {running ? 'Building…' : `▶ Build ${soNumbers.length || ''} card${soNumbers.length === 1 ? '' : 's'}`}
        </button>
      </div>

      {error && <p className="report-note">{error}</p>}

      <h3>Log</h3>
      <pre className="report-box">
        {log || '—'}
      </pre>

      <h3>Cards</h3>
      {cards.length === 0 ? (
        <p className="muted">No cards yet.</p>
      ) : (
        <ul className="notice-cards">
          {cards.map((c) => (
            <li key={c.name}>
              <a href={noticeCardUrl(c.name)} target="_blank" rel="noreferrer">
                {/* Full-size cards are ~10 MB and 7000px wide, so the thumbnail
                    is the same file scaled by the browser; the link opens it. */}
                <img src={noticeCardUrl(c.name)} alt={c.name} loading="lazy" />
                <span>{c.name}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
