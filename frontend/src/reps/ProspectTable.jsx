// Prospect rows beneath the map. Read-only apart from the "mark" toggle, which
// is the rep's own shortlist and the only thing on this page they can change.
//
// Written separately from RepOrderTable for the same reason that one was split
// from admin's OrderTable: shared table components accrete columns that only
// one caller may show, and this page must never be able to render an order's
// dollar value or card state by accident.

const DASH = <span className="unknown">—</span>

export default function ProspectTable({ rows, onFocus, onToggleMark, busyId }) {
  if (rows.length === 0) {
    return (
      <table className="admin-table">
        <tbody>
          <tr>
            <td className="admin-empty-row">No prospects match these filters.</td>
          </tr>
        </tbody>
      </table>
    )
  }

  return (
    <table className="admin-table prospect-table">
      <thead>
        <tr>
          <th aria-label="Shortlist" />
          <th>Store</th>
          <th>Where</th>
          <th className="num">Rating</th>
          <th>Contact</th>
          <th>Nearest stockist</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          // The whole row is the map control: clicking anywhere flies to the
          // store, so a rep reading the list never has to hunt for its dot.
          <tr
            key={p.id}
            className={p.potentialConflict ? 'row-conflict' : undefined}
            onClick={() => onFocus(p)}
          >
            <td>
              <button
                type="button"
                className={p.marked ? 'mark-btn marked' : 'mark-btn'}
                disabled={busyId === p.id}
                title={p.marked ? 'Remove from your shortlist' : 'Add to your shortlist'}
                onClick={(e) => {
                  e.stopPropagation() // don't also fly the map
                  onToggleMark(p)
                }}
              >
                {p.marked ? '★' : '☆'}
              </button>
            </td>
            <td>
              <div className="cert-missing">
                <span>{p.storeName}</span>
                {/* Only shown when OSM positively said so — an absent tag is
                    not evidence either way, so there is no "no" badge. */}
                {p.womenswear && <span className="sub badge-women">womenswear</span>}
              </div>
            </td>
            <td>
              <div className="cert-missing">
                <span>{p.city || DASH}</span>
                {p.address && <span className="sub">{p.address}</span>}
              </div>
            </td>
            <td className="num">
              {p.rating == null ? (
                DASH
              ) : (
                <div className="cert-missing">
                  <span>{p.rating}</span>
                  {p.reviewCount != null && <span className="sub">{p.reviewCount} reviews</span>}
                </div>
              )}
            </td>
            <td>
              <div className="cert-missing">
                {p.website ? (
                  <a
                    href={p.website}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    website
                  </a>
                ) : (
                  DASH
                )}
                {p.phone && <span className="sub">{p.phone}</span>}
              </div>
            </td>
            <td>
              {p.nearestStockist ? (
                <div className="cert-missing">
                  <span>{p.nearestStockist}</span>
                  {p.distanceMiles != null && (
                    <span className="sub">
                      {p.distanceMiles} mi
                      {p.potentialConflict ? ' — within catchment' : ''}
                    </span>
                  )}
                </div>
              ) : (
                DASH
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
