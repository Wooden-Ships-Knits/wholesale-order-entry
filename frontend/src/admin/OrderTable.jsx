import { useState } from 'react'
import { certUrl, getConflictEmail, pdfUrl, setOrderStatus } from './api'
import EmailDraftModal from '../components/EmailDraftModal'

// null means unanswered / not yet checked — never render that as "No".
// `tone` tints the cell only when the answer is Yes (green/red as given).
function YesNoCell({ value, tone }) {
  if (value === null || value === undefined) return <td><span className="unknown">—</span></td>
  return <td className={value ? `flag-${tone}` : undefined}>{value ? 'Yes' : 'No'}</td>
}

export default function OrderTable({ orders, onChanged, onError }) {
  const [draft, setDraft] = useState(null)
  const [drafting, setDrafting] = useState(null) // id of the order being drafted

  async function draftEmail(order) {
    setDrafting(order.id)
    try {
      const d = await getConflictEmail({ orderId: order.id })
      setDraft({ ...d, title: 'Conflict email draft' })
    } catch (err) {
      onError(err.message)
    } finally {
      setDrafting(null)
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
    })
  }

  async function decide(order, status) {
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
      {draft && <EmailDraftModal draft={draft} onClose={() => setDraft(null)} />}
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
              <YesNoCell value={o.isNewAccount} tone="green" />
              {/* Conflict + its email action combined into one cell.
                  No conflict (or not yet checked) shows "No" — never blank. */}
              <td className={o.hasConflict ? 'flag-red' : undefined}>
                {o.hasConflict ? (
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      gap: '4px',
                    }}
                  >
                    <span>Yes</span>
                    <button
                      type="button"
                      className="chip"
                      disabled={drafting === o.id}
                      onClick={() => draftEmail(o)}
                    >
                      {drafting === o.id ? 'Drafting…' : 'Send Email'}
                    </button>
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
                  /* new account, no cert uploaded → offer to request one */
                  <button type="button" className="chip" onClick={() => requestTaxCert(o)}>
                    Generate email
                  </button>
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
                  <span className={`status ${o.status}`} title={o.statusReason || ''}>
                    {o.status}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
