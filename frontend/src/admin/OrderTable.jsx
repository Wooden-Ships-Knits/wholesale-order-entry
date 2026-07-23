import { useState } from 'react'
import { certUrl, createSfAccount, getConflictEmail, pdfUrl, setOrderStatus } from './api'
import EmailDraftModal from '../components/EmailDraftModal'

// Always render Yes / No (never blank) — null/undefined is treated as No.
// `tone` tints the cell only when the answer is Yes (green/red as given).
function YesNoCell({ value, tone }) {
  const yes = Boolean(value)
  return <td className={yes ? `flag-${tone}` : undefined}>{yes ? 'Yes' : 'No'}</td>
}

export default function OrderTable({ orders, onChanged, onError }) {
  const [draft, setDraft] = useState(null)
  const [drafting, setDrafting] = useState(null) // id of the order being drafted
  const [creating, setCreating] = useState(null) // id of the order whose SF account is being created
  const [sentConflict, setSentConflict] = useState(() => new Set()) // orders whose conflict email was sent
  const [sentTaxCert, setSentTaxCert] = useState(() => new Set()) // orders whose tax-cert email was sent

  // Create the Salesforce Business Account for a new-account order. This is a
  // live-org write, so confirm first; the backend is idempotent as a backstop.
  async function createAccount(order) {
    const name = order.accountName || 'this store'
    if (
      !window.confirm(
        `Create a Salesforce Business Account for "${name}"?\n\n` +
          'This writes to the live Salesforce org and cannot be undone from here.',
      )
    )
      return
    setCreating(order.id)
    try {
      await createSfAccount(order.id)
      onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setCreating(null)
    }
  }

  async function draftEmail(order) {
    setDrafting(order.id)
    try {
      const d = await getConflictEmail({ orderId: order.id })
      // conflictOrderId marks this as a conflict draft so a successful send
      // flips that order's button to "Sent" (tax-cert drafts don't set it).
      setDraft({ ...d, title: 'Conflict email draft', conflictOrderId: order.id })
    } catch (err) {
      onError(err.message)
    } finally {
      setDrafting(null)
    }
  }

  function handleSent() {
    if (draft?.conflictOrderId) {
      setSentConflict((prev) => new Set(prev).add(draft.conflictOrderId))
    }
    if (draft?.taxCertOrderId) {
      setSentTaxCert((prev) => new Set(prev).add(draft.taxCertOrderId))
    }
  }

  // Request a tax-exemption certificate from a new account that didn't upload
  // one. Recipient is left blank (the rep's email is filled in by hand).
  function requestTaxCert(order) {
    const name = order.accountName || order.buyerName || 'your store'
    setDraft({
      to: '',
      subject: `New Account Info Required - ${name}`,
      body:
        'Hi Wooden Ships Retailer,\n\n' +
        'Thank you for your support as a new Wooden Ships Retailer! We so appreciate your support.\n\n' +
        'Please note that a copy of your Resale Certificate is required to complete your status as a ' +
        'Wooden Ships Retailer. Please reply to this email with your state-issued Sales Tax Exemption ' +
        'form as soon as possible.\n\n' +
        'Best,\n' +
        'Wooden Ships',
      title: 'Tax certificate request',
      // taxCertOrderId marks this as a tax-cert draft so a successful send
      // flips that order's button to "Sent".
      taxCertOrderId: order.id,
    })
  }

  async function decide(order, status) {
    // Accept now also pushes the order into Salesforce (Kugamon Draft), so
    // confirm the live-org write first.
    if (status === 'accepted') {
      const name = order.accountName || 'this order'
      if (
        !window.confirm(
          `Accept "${name}" and create the order in Salesforce (Kugamon Draft)?\n\n` +
            'For a new account, create its Salesforce account first.',
        )
      )
        return
    }
    const reason =
      status === 'declined' ? window.prompt('Reason for declining (optional):') ?? '' : ''
    try {
      await setOrderStatus(order.id, status, reason)
      onChanged()
    } catch (err) {
      onError(err.message)
    }
  }

  if (!orders.length) return <p className="admin-empty">No orders yet.</p>

  return (
    <>
      {draft && (
        <EmailDraftModal draft={draft} onClose={() => setDraft(null)} onSent={handleSent} />
      )}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Account Name</th>
            <th>Sales Territory</th>
            <th>Special Instruction</th>
            <th>New account</th>
            <th>Potential conflict</th>
            <th>Tax certificate</th>
            <th>Notes</th>
            <th>Decision</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id}>
              <td title={o.id}>
                <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                  <code>{o.shortId}</code>
                </a>
              </td>
              <td>{o.accountName || <span className="unknown">—</span>}</td>
              <td>{o.salesTerritory || <span className="unknown">—</span>}</td>
              <td className="notes-cell" title={o.specialInstructions || ''}>
                {o.specialInstructions || <span className="unknown">—</span>}
              </td>
              {/* New account = Yes stacks a "Create account" action (or the
                  "Created ✓" state) beneath it, like the tax-cert cell. */}
              <td>
                {o.isNewAccount ? (
                  <div className="cert-missing">
                    <span>Yes</span>
                    {o.sfAccountId ? (
                      <span className="sf-created" title={o.sfAccountId}>
                        Created ✓
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="chip"
                        disabled={creating === o.id}
                        onClick={() => createAccount(o)}
                      >
                        {creating === o.id ? 'Creating…' : 'Create account'}
                      </button>
                    )}
                  </div>
                ) : (
                  'No'
                )}
              </td>
              {/* Conflict + its email action combined into one cell.
                  No conflict (or not yet checked) shows "No" — never blank. */}
              <td>
                {o.hasConflict ? (
                  <div className="cert-missing">
                    <span>Yes</span>
                    {o.conflictEmailSent || sentConflict.has(o.id) ? (
                      <span className="sf-created">Sent ✓</span>
                    ) : (
                      <button
                        type="button"
                        className="chip"
                        disabled={drafting === o.id}
                        onClick={() => draftEmail(o)}
                      >
                        {drafting === o.id ? 'Generating…' : 'Generate email'}
                      </button>
                    )}
                  </div>
                ) : (
                  'No'
                )}
              </td>
              <td>
                {o.hasCertificate ? (
                  <a href={certUrl(o.id)} target="_blank" rel="noreferrer">
                    Open
                  </a>
                ) : o.isNewAccount ? (
                  /* new account, no cert uploaded → show No + offer to request one */
                  <div className="cert-missing">
                    <span>No</span>
                    {o.taxCertEmailSent || sentTaxCert.has(o.id) ? (
                      <span className="sf-created">Sent ✓</span>
                    ) : (
                      <button type="button" className="chip" onClick={() => requestTaxCert(o)}>
                        Generate email
                      </button>
                    )}
                  </div>
                ) : (
                  <span className="unknown">—</span>
                )}
              </td>
              <td className="notes-cell" title={o.notes || ''}>
                {o.notes || <span className="unknown">—</span>}
              </td>
              <td>
                {o.status === 'submitted' ? (
                  <div className="decide">
                    <button type="button" className="accept" onClick={() => decide(o, 'accepted')}>
                      Accept
                    </button>
                    <button type="button" className="decline" onClick={() => decide(o, 'declined')}>
                      Decline
                    </button>
                  </div>
                ) : (
                  <div className="cert-missing">
                    <span className={`status ${o.status}`} title={o.statusReason || ''}>
                      {o.status}
                    </span>
                    {o.sfOrderNumber && (
                      <span className="sf-created" title={o.sfOrderId}>
                        {o.sfOrderNumber}
                      </span>
                    )}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
