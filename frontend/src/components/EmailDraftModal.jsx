import { useState } from 'react'

/**
 * Popup showing an email draft (conflict-inquiry from POST /api/conflict-email,
 * or a tax-certificate request). The draft is editable; "Send Mail" hands it to
 * the server's SMTP account via POST /api/send-email. To and CC are required.
 */
export default function EmailDraftModal({ draft, onClose, onSent }) {
  const [to, setTo] = useState(draft.to || '')
  const [cc, setCc] = useState(draft.cc || '')
  const [subject, setSubject] = useState(draft.subject || '')
  const [body, setBody] = useState(draft.body || '')
  const [copied, setCopied] = useState(false)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [sendError, setSendError] = useState('')

  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  // Conflict emails have no CC (hideCc); tax-cert CC is the rep and may be
  // empty when the territory is unknown. So only To is required.
  const showCc = !draft.hideCc
  const toMissing = !to.trim()
  const canSend = !toMissing && !sending && !sent

  // Tie this draft to an order so a successful send is recorded server-side
  // (persistent "Sent ✓"). Tax-cert and conflict drafts carry different ids.
  const orderId = draft.conflictOrderId || draft.taxCertOrderId || null
  const kind = draft.conflictOrderId ? 'conflict' : draft.taxCertOrderId ? 'tax_cert' : null

  async function send() {
    const ccNote = cc.trim() ? ` (cc ${cc.trim()})` : ''
    if (!window.confirm(`Send this email to ${to.trim()}${ccNote}?`)) return
    setSending(true)
    setSendError('')
    try {
      const res = await fetch('/api/send-email', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: to.trim(), cc: cc.trim(), subject, body, orderId, kind }),
      })
      if (!res.ok) {
        const b = await res.json().catch(() => ({}))
        throw new Error(b.detail || `Send failed (${res.status})`)
      }
      setSent(true)
      onSent?.()
    } catch (e) {
      setSendError(e.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="conflict-modal-overlay" onClick={onClose}>
      <div
        className="conflict-modal email-modal"
        role="dialog"
        aria-modal="true"
        aria-label={draft.title || 'Email draft'}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{draft.title || 'Email draft'}</h2>
        <p className="conflict-modal-note">
          Review and edit the draft, then send it from wholesale@wooden-ships.com — or copy the text.
        </p>

        <label>
          To<span className="req">*</span>
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            aria-required="true"
          />
          {toMissing && <span className="field-warning">To is required.</span>}
        </label>
        {showCc && (
          <label>
            CC
            <input
              value={cc}
              onChange={(e) => setCc(e.target.value)}
              placeholder="name@example.com, another@example.com"
            />
          </label>
        )}
        <label>
          Subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label>
          Message
          <textarea rows="14" value={body} onChange={(e) => setBody(e.target.value)} />
        </label>

        {sent && <p className="send-status ok">Email sent.</p>}
        {sendError && <p className="send-status err">{sendError}</p>}

        <div className="conflict-modal-actions email-modal-actions">
          <button type="button" className="link-btn" onClick={onClose}>
            {sent ? 'Close' : 'Cancel'}
          </button>
          <button type="button" onClick={copy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            type="button"
            className="btn-link"
            onClick={send}
            disabled={!canSend}
            title={toMissing ? 'Fill in the required To field first' : undefined}
          >
            {sending ? 'Sending…' : sent ? 'Sent' : 'Send Mail'}
          </button>
        </div>
      </div>
    </div>
  )
}
