import { certUrl, pdfUrl, setOrderStatus } from './api'

// null means unanswered / not yet checked — never render that as "No".
// `tone` tints the cell only when the answer is Yes (green/red as given).
function YesNoCell({ value, tone }) {
  if (value === null || value === undefined) return <td><span className="unknown">—</span></td>
  return <td className={value ? `flag-${tone}` : undefined}>{value ? 'Yes' : 'No'}</td>
}

export default function OrderTable({ orders, onChanged, onError }) {
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
    <table className="admin-table">
      <thead>
        <tr>
          <th>Order ID</th>
          <th>Account Name</th>
          <th>Sales Territory</th>
          <th>PDF</th>
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
              <code>{o.shortId}</code>
            </td>
            <td>{o.accountName || <span className="unknown">—</span>}</td>
            <td>{o.salesTerritory || <span className="unknown">—</span>}</td>
            <td>
              <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                Open PDF
              </a>
            </td>
            <YesNoCell value={o.isNewAccount} tone="green" />
            <YesNoCell value={o.hasConflict} tone="red" />
            <td>
              {o.hasCertificate ? (
                <a href={certUrl(o.id)} target="_blank" rel="noreferrer">
                  Open
                </a>
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
  )
}
