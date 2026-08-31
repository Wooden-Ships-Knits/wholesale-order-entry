// The rep's order table: twelve read-only columns, with a per-column filter
// row under the headers. The only action is the Order ID link, which opens
// that order's buyer-facing PDF.
//
// Styling reuses the .admin-table classes so the two internal pages read as one
// product. The cells are written here rather than shared with OrderTable
// because every admin cell is wrapped around a button a rep must never see.

import { useEffect, useMemo, useRef } from 'react'
import { pdfUrl } from './api'
import { distinctValues, STATUS_FILTERS } from './filterOrders'

const DASH = <span className="unknown">—</span>

// Same format as /admin and the signing page, so an amount reads identically
// wherever it appears.
const money = (n) =>
  (Number(n) || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' })

function shortDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Buyer signature by emailed link. Same three states and colours as /admin:
 *    green + empty — no signature needed; the form was signed on the spot
 *    yellow        — link is out, still waiting on the buyer
 *    green + name  — signed
 *  The read-only half of the admin cell: no send, resend or cancel. */
function SignatureCell({ order: o }) {
  // Signed on the form itself — a customer-filled order, signed at submit with
  // no link ever sent. Says so rather than showing blank, which read as "still
  // waiting" for the one case needing no chasing. Same wording as /admin.
  if (!o.signatureRequested) {
    if (!o.signatureName) return <td className="flag-green" />
    return (
      <td className="flag-green">
        <div className="cert-missing">
          <span className="sf-created">Signed ✓</span>
          <span className="sub">{o.signatureName}</span>
          {o.signatureDate && <span className="sub">{shortDate(o.signatureDate)}</span>}
          <span className="sub">on the form</span>
        </div>
      </td>
    )
  }

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

export default function RepOrderTable({
  orders, // already filtered by RepsApp
  allOrders, // unfiltered, so the dropdown options don't shrink as you filter
  filters,
  onFilterChange,
  statusFilter, // the server-side Decision filter, shared with the toolbar chips
  onStatusFilterChange,
}) {
  // Dropdown options come from the unfiltered rows: picking a territory must
  // not remove the other territories from the list you picked it from.
  const seasons = useMemo(() => distinctValues(allOrders, (o) => o.seasonCode), [allOrders])
  const shipWindows = useMemo(() => distinctValues(allOrders, (o) => o.shipWindow), [allOrders])
  const writers = useMemo(() => distinctValues(allOrders, (o) => o.orderWrittenBy), [allOrders])
  const territories = useMemo(() => distinctValues(allOrders, (o) => o.salesTerritory), [allOrders])

  // Both header rows are sticky, so the filter row has to sit exactly at the
  // label row's height. That height isn't knowable in CSS — labels wrap
  // differently as column widths, zoom and the loaded font change — so measure
  // it and publish it as --admin-head-h, same as /admin's table does.
  const headRowRef = useRef(null)
  useEffect(() => {
    const row = headRowRef.current
    if (!row) return
    const table = row.closest('table')
    const sync = () => table?.style.setProperty('--admin-head-h', `${row.offsetHeight}px`)
    sync()
    const observer = new ResizeObserver(sync)
    observer.observe(row)
    return () => observer.disconnect()
  }, [])

  return (
    <table className="admin-table">
      <thead>
        <tr ref={headRowRef}>
          <th>Date</th>
          <th>Order ID</th>
          <th>Signature</th>
          <th>Season</th>
          <th>QTY</th>
          <th>Ship Window</th>
          <th>Account Name</th>
          <th>Value</th>
          <th>Written By</th>
          <th>Sales Territory</th>
          <th>Notes</th>
          <th>Decision</th>
        </tr>
        {/* Per-column filters, same controls as /admin. Every cell is bound to
            one key of the `filters` object owned by RepsApp ('' = no filter),
            except Decision, which drives the server-side status filter the
            toolbar chips also set — one column, one control. */}
        <tr className="filter-row">
          <th>
            {/* <label> wraps each input, so the word is also the accessible
                name and clicking it focuses the field. */}
            <div className="filter-range">
              <label>
                <span>From</span>
                <input
                  type="date"
                  value={filters.dateFrom}
                  max={filters.dateTo || undefined}
                  onChange={(e) => onFilterChange('dateFrom', e.target.value)}
                />
              </label>
              <label>
                <span>To</span>
                <input
                  type="date"
                  value={filters.dateTo}
                  min={filters.dateFrom || undefined}
                  onChange={(e) => onFilterChange('dateTo', e.target.value)}
                />
              </label>
            </div>
          </th>
          <th>
            <input
              type="search"
              placeholder="ID"
              aria-label="Filter by order ID"
              value={filters.shortId}
              onChange={(e) => onFilterChange('shortId', e.target.value)}
            />
          </th>
          <th>
            {/* Fixed options, not distinctValues: "Unsigned" has to stay
                selectable even when nothing is currently unsigned, which is
                exactly when someone wants to check. */}
            <select
              aria-label="Filter by signature"
              value={filters.sign}
              onChange={(e) => onFilterChange('sign', e.target.value)}
            >
              <option value="">All</option>
              <option value="yes">Signed</option>
              <option value="no">Unsigned</option>
            </select>
          </th>
          <th>
            <select
              aria-label="Filter by season"
              value={filters.season}
              onChange={(e) => onFilterChange('season', e.target.value)}
            >
              <option value="">All</option>
              {seasons.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </th>
          {/* QTY has no filter: a free-text or range control over a number
              nobody searches by would cost a column of width for nothing. The
              header row still needs the cell to stay aligned — one per column,
              or everything to the right shifts. */}
          <th aria-hidden="true" />
          <th>
            <select
              aria-label="Filter by shipping window"
              value={filters.shipWindow}
              onChange={(e) => onFilterChange('shipWindow', e.target.value)}
            >
              <option value="">All</option>
              {shipWindows.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </th>
          <th>
            <input
              type="search"
              placeholder="Search…"
              aria-label="Filter by account name"
              value={filters.accountName}
              onChange={(e) => onFilterChange('accountName', e.target.value)}
            />
          </th>
          {/* Value: unfiltered, same reasoning as QTY. */}
          <th aria-hidden="true" />
          <th>
            <select
              aria-label="Filter by Written By"
              value={filters.writtenBy}
              onChange={(e) => onFilterChange('writtenBy', e.target.value)}
            >
              <option value="">All</option>
              {writers.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </th>
          <th>
            <select
              aria-label="Filter by sales territory"
              value={filters.territory}
              onChange={(e) => onFilterChange('territory', e.target.value)}
            >
              <option value="">All</option>
              {territories.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </th>
          <th>
            <input
              type="search"
              placeholder="Search…"
              aria-label="Filter by notes"
              value={filters.notes}
              onChange={(e) => onFilterChange('notes', e.target.value)}
            />
          </th>
          <th>
            {/* Bound to the same state as the toolbar chips — changing either
                one moves the other, and the rows are re-fetched server-side. */}
            <select
              aria-label="Filter by decision"
              value={statusFilter}
              onChange={(e) => onStatusFilterChange(e.target.value)}
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </th>
        </tr>
      </thead>
      <tbody>
        {orders.length === 0 && (
          <tr>
            <td className="admin-empty-row" colSpan={12}>
              {allOrders.length ? 'No orders match these filters.' : 'No orders yet.'}
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
              {/* Reps are spread across time zones and the office is not in
                  any of them, so a bare clock time is ambiguous. Same format
                  as /admin. */}
              <span className="sub">
                {new Date(o.createdAt).toLocaleTimeString('en-US', {
                  hour: 'numeric',
                  minute: '2-digit',
                  timeZoneName: 'shortOffset',
                })}
              </span>
            </td>
            {/* Opens the buyer-facing PDF in a new tab, same as /admin. */}
            <td title={o.id}>
              <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                <code>{o.shortId}</code>
              </a>
            </td>
            <SignatureCell order={o} />
            <td>{o.seasonCode}</td>
            <td className="num">{o.totalQty}</td>
            <td>{o.shipWindow || DASH}</td>
            <td>{o.accountName || DASH}</td>
            <td className="num">
              {o.totalAmount == null ? DASH : money(o.totalAmount)}
            </td>
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
