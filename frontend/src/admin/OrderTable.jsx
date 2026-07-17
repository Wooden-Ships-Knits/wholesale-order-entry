import { certUrl, pdfUrl, setOrderStatus } from './api'

// null means unanswered / not yet checked — never render that as "No".
function YesNo({ value }) {
  if (value === null || value === undefined) return <span className="unknown">—</span>
  return value ? 'Yes' : 'No'
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
              <div className="sub">{o.buyerName || o.shipEmail}</div>
            </td>
            <td>
              <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                Open PDF
              </a>
            </td>
            <td>
              <YesNo value={o.isNewAccount} />
            </td>
            <td>
              <YesNo value={o.hasConflict} />
            </td>
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
