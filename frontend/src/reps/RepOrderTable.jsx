// The rep's order table: eleven read-only columns, no actions.
//
// Styling reuses the .admin-table classes so the two internal pages read as one
// product. The cells are written here rather than shared with OrderTable
// because every admin cell is wrapped around a button a rep must never see.

const DASH = <span className="unknown">—</span>

function shortDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Buyer signature by emailed link. Same three states and colours as /admin:
 *    green + empty — no signature needed; the form was signed on the spot
 *    yellow        — link is out, still waiting on the buyer
 *    green + name  — signed
 *  The read-only half of the admin cell: no send, resend or cancel. */
function SignatureCell({ order: o }) {
  // Deliberately empty: a "—" here would read as missing data rather than
  // "not applicable".
  if (!o.signatureRequested) return <td className="flag-green" />

  if (o.signatureSignedAt) {
    return (
      <td className="flag-green">
        <div className="cert-missing">
          <span className="sf-created">Signed ✓</span>
          <span className="sub">{o.signatureName}</span>
          <span className="sub">{shortDate(o.signatureSignedAt)}</span>
          {/* The buyer may have changed quantities before signing. Say so, or
              the rep's copy and the accepted order silently disagree. */}
          {o.signatureEdited && (
            <span className="sub sig-edited" title="The buyer changed the order before signing">
              edited: {o.origTotalQty} → {o.totalQty} pcs
            </span>
          )}
        </div>
      </td>
    )
  }

  return (
    <td className="flag-yellow">
      <div className="cert-missing">
        {o.signatureEmailSent ? (
          <span className="sf-created">Email sent ✓ waiting for signature</span>
        ) : (
          /* The office has to send this by hand — say so rather than showing a
             reassuring "sent" the buyer never received. */
          <span className="sig-unsent">Not sent yet — the office will send it</span>
        )}
        {o.signatureEmail && <span className="sub">{o.signatureEmail}</span>}
      </div>
    </td>
  )
}

/** Accept / decline as the office recorded it. Read-only here — a pending order
 *  says so instead of offering buttons the rep cannot press. */
function DecisionCell({ order: o }) {
  if (o.status === 'submitted') {
    return (
      <td>
        <span className="sub">Awaiting review</span>
      </td>
    )
  }
  return (
    <td>
      <div className="cert-missing">
        <span className={`status ${o.status}`}>{o.status}</span>
        {o.statusReason && <span className="sub">{o.statusReason}</span>}
        {o.statusAt && <span className="sub">{shortDate(o.statusAt)}</span>}
      </div>
    </td>
  )
}

export default function RepOrderTable({ orders }) {
  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Order ID</th>
          <th>Signature</th>
          <th>Season</th>
          <th>Quantity</th>
          <th>Shipping Window</th>
          <th>Account Name</th>
          <th>Written By</th>
          <th>Sales Territory</th>
          <th>Notes</th>
          <th>Decision</th>
        </tr>
      </thead>
      <tbody>
        {orders.length === 0 && (
          <tr>
            <td className="admin-empty-row" colSpan={11}>
              No orders yet.
            </td>
          </tr>
        )}
        {orders.map((o) => (
          <tr key={o.shortId}>
            <td className="date-cell">
              <span>
                {new Date(o.createdAt).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
              <span className="sub">
                {new Date(o.createdAt).toLocaleTimeString('en-US', {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
              </span>
            </td>
            <td>{o.shortId}</td>
            <SignatureCell order={o} />
            <td>{o.seasonCode}</td>
            <td className="num">{o.totalQty}</td>
            <td>{o.shipWindow || DASH}</td>
            <td>{o.accountName || DASH}</td>
            <td>{o.orderWrittenBy || DASH}</td>
            <td>{o.salesTerritory || DASH}</td>
            <td className="notes-cell" title={o.notes || ''}>
              {o.notes || DASH}
            </td>
            <DecisionCell order={o} />
          </tr>
        ))}
      </tbody>
    </table>
  )
}
