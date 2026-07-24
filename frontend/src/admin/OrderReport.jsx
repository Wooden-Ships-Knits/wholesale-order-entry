import { useEffect, useState } from 'react'
import { getReport, runReport } from './api'

// The automation reports surfaced in /admin. `ready` = the backend runner
// exists (backend/app/routers/reports.py _RUNNERS); DMM is not ported yet.
const REPORTS = [
  {
    key: 'dto',
    ready: true,
    title: 'DTO — Daily Total Order',
    description:
      "Pull today's Salesforce 'Daily Total Order' report and draft the recap email with a per-rep breakdown.",
  },
  {
    key: 'dmm',
    ready: false,
    title: 'DMM — Daily Morning Meeting',
    description: "Pull today's summary of unpaid sales orders and draft the recap text.",
  },
]

function ReportCard({ report }) {
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState('')
  const [output, setOutput] = useState('')
  const [ranAt, setRanAt] = useState(null)
  const [error, setError] = useState('')

  // A run result → the card's fields (log is a list of lines from the backend).
  function apply(d) {
    if (!d.ran) return
    setLog((d.log || []).join('\n'))
    setOutput(d.recap || '')
    setRanAt(d.ranAt || null)
  }

  // Show the last cached run when the tab opens — so "run once, stays there".
  useEffect(() => {
    if (!report.ready) return
    let stale = false
    getReport(report.key)
      .then((d) => !stale && apply(d))
      .catch(() => {})
    return () => {
      stale = true
    }
  }, [report.key, report.ready])

  async function run() {
    setRunning(true)
    setError('')
    try {
      apply(await runReport(report.key))
    } catch (e) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="report-card">
      <h2>{report.title}</h2>
      <p className="muted">{report.description}</p>

      <div className="report-run-row">
        <button
          type="button"
          className="report-run"
          onClick={run}
          disabled={running || !report.ready}
        >
          {!report.ready ? 'Coming soon' : running ? 'Running…' : '▶ Run report'}
        </button>
        {ranAt && <span className="report-ranat">Last run: {new Date(ranAt).toLocaleString()}</span>}
      </div>
      {error && <p className="report-note">{error}</p>}

      <h3>Log</h3>
      <pre className="report-box">{log || '—'}</pre>

      <h3>Output</h3>
      <pre className="report-box">{output || '—'}</pre>
    </section>
  )
}

export default function OrderReport() {
  return (
    <div className="report-grid">
      {REPORTS.map((r) => (
        <ReportCard key={r.key} report={r} />
      ))}
    </div>
  )
}
