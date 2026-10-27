import { useEffect, useState } from 'react'
import { getReport, reportFileUrl, runReport } from './api'

// The automation reports surfaced in /admin. `ready` = the backend runner
// exists (backend/app/routers/reports.py _RUNNERS).
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
    ready: true,
    title: 'DMM — Daily Morning Meeting',
    description:
      "Pull today's shipping plan and unpaid open orders, and draft the morning-meeting recap.",
  },
  {
    key: 'oo',
    ready: true,
    title: 'OO — Open Order',
    description:
      "Pull the Salesforce 'Rep Open Order Detail Report' up to today and download a zip of colour-coded spreadsheets: the Master plus one file per rep and a House file, with split orders copied to the rep they're split with. Yellow = entered last week, orange = within the ship window, red = past it.",
  },
]

function ReportCard({ report }) {
  const [running, setRunning] = useState(false)
  const [log, setLog] = useState('')
  const [output, setOutput] = useState('')
  const [ranAt, setRanAt] = useState(null)
  const [download, setDownload] = useState(null) // filename of the last run's file, if any
  const [error, setError] = useState('')
  const [copied, setCopied] = useState('') // '' | 'ok' | 'failed'

  // The output goes straight into WhatsApp, so copy it exactly as shown.
  async function copyOutput() {
    try {
      await navigator.clipboard.writeText(output)
      setCopied('ok')
    } catch {
      setCopied('failed')
    }
    setTimeout(() => setCopied(''), 2000)
  }

  // A run result → the card's fields (log is a list of lines from the backend).
  function apply(d) {
    if (!d.ran) return
    setLog((d.log || []).join('\n'))
    setOutput(d.recap || '')
    setRanAt(d.ranAt || null)
    setDownload(d.download || null)
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
      {/* A plain link: the browser downloads it with the admin cookie, and the
          file is the one the last run built — re-run to refresh it. */}
      {download && !running && (
        <p className="report-download">
          <a href={reportFileUrl(report.key)} download={download}>
            ⬇ Download {download}
          </a>
        </p>
      )}
      {error && <p className="report-note">{error}</p>}

      <h3>Log</h3>
      <pre className="report-box">{log || '—'}</pre>

      <div className="report-output-head">
        <h3>Output</h3>
        {output && (
          <button type="button" className="report-copy" onClick={copyOutput}>
            {copied === 'ok' ? '✓ Copied' : copied === 'failed' ? 'Copy failed' : '⧉ Copy'}
          </button>
        )}
      </div>
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
