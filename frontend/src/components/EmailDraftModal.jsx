import { useState } from 'react'

/**
 * Popup showing the conflict email draft returned by POST /api/conflict-email.
 * The draft is editable — nothing is sent from here; the user copies it or
 * hands it to their own mail client.
 */
export default function EmailDraftModal({ draft, onClose }) {
  const [to, setTo] = useState(draft.to || '')
  const [subject, setSubject] = useState(draft.subject || '')
  const [body, setBody] = useState(draft.body || '')
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  const mailto = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(
    subject,
  )}&body=${encodeURIComponent(body)}`

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
          Nothing is sent from here — review, edit, then copy it or open it in your mail app.
        </p>

        <label>
          To
          <input value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <label>
          Subject
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label>
          Message
          <textarea rows="14" value={body} onChange={(e) => setBody(e.target.value)} />
        </label>

        <div className="conflict-modal-actions email-modal-actions">
          <button type="button" className="link-btn" onClick={onClose}>
            Close
          </button>
          <button type="button" onClick={copy}>
            {copied ? 'Copied' : 'Copy'}
          </button>
          <a className="btn-link" href={mailto}>
            Open in mail app
          </a>
        </div>
      </div>
    </div>
  )
}
