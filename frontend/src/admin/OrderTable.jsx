import { useMemo, useState } from 'react'
import { certUrl, createSfAccount, getConflictEmail, pdfUrl, setOrderStatus } from './api'
import { distinctValues, rankCode } from './filterOrders'
import EmailDraftModal from '../components/EmailDraftModal'

// Salesforce My Domain — the pushed order record opens at <instance>/<recordId>.
// Change this if the org's domain changes (e.g. a sandbox).
const SF_INSTANCE_URL = 'https://wooden-ships.my.salesforce.com'

// Always render Yes / No (never blank) — null/undefined is treated as No.
// `tone` tints the cell only when the answer is Yes (green/red as given).
function YesNoCell({ value, tone }) {
  const yes = Boolean(value)
  return <td className={yes ? `flag-${tone}` : undefined}>{yes ? 'Yes' : 'No'}</td>
}

// Tri-state dropdown for the boolean columns; '' = no filter.
function YesNoFilter({ label, value, onChange }) {
  return (
    <select
      aria-label={`Filter by ${label}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">All</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>
  )
}

export default function OrderTable({
  orders, // already filtered by AdminApp
  allOrders, // unfiltered, so the dropdown options don't shrink as you filter
  filters,
  onFilterChange,
  onChanged,
  onError,
}) {
  const [draft, setDraft] = useState(null)
  const [drafting, setDrafting] = useState(null) // id of the order being drafted
  const [creating, setCreating] = useState(null) // id of the order whose SF account is being created
  const [sentConflict, setSentConflict] = useState(() => new Set()) // orders whose conflict email was sent
  const [sentTaxCert, setSentTaxCert] = useState(() => new Set()) // orders whose tax-cert email was sent

  // Dropdown options come from the unfiltered rows: picking a territory must
  // not remove the other territories from the list you picked it from.
  const territories = useMemo(() => distinctValues(allOrders, (o) => o.salesTerritory), [allOrders])
  const ranks = useMemo(() => distinctValues(allOrders, (o) => rankCode(o.rank)), [allOrders])

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
      // Conflict email goes to the affected rep only — no CC.
      setDraft({ ...d, title: 'Conflict email draft', conflictOrderId: order.id, hideCc: true })
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
      // Sent to the buyer (Ship To email); the rep is CC'd (by sales territory).
      // Either may be empty — the admin fills in what's missing before sending.
      to: order.shipEmail || '',
      cc: order.repEmail || '',
      subject: `Tax Certificate Request - ${name}`,
      body:
        'Hi,\n\n' +
        'Thank you for your support as a new Wooden Ships Retailer! We so appreciate your support.\n\n' +
        'Please note that a copy of your Resale Certificate is required to complete your status as a ' +
        'Wooden Ships Retailer.\n\n' +
        'Please reply to this email with your state-issued Sales Tax Exemption ' +
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

  // No early return on an empty list: the filter row lives in <thead>, so
  // bailing out here would hide the very controls needed to undo a filter that
  // matched nothing. The empty state is a row inside <tbody> instead.
  return (
    <>
      {draft && (
        <EmailDraftModal draft={draft} onClose={() => setDraft(null)} onSent={handleSent} />
      )}
      <table className="admin-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Order ID</th>
            <th>Account Name</th>
            <th>Sales Territory</th>
            <th>New account</th>
            <th>Rank</th>
            <th>Potential conflict</th>
            <th>Tax certificate</th>
            <th>Notes</th>
            <th>Special Instruction</th>
            <th>Decision</th>
          </tr>
          {/* Per-column filters. Every cell is controlled by one key of the
              `filters` object owned by AdminApp; '' means "no filter". The
              Decision column reuses the toolbar's status filter (server-side)
              so there is only ever one status control. */}
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
              <input
                type="search"
                placeholder="Search…"
                aria-label="Filter by account name"
                value={filters.accountName}
                onChange={(e) => onFilterChange('accountName', e.target.value)}
              />
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
              <YesNoFilter
                label="new account"
                value={filters.newAccount}
                onChange={(v) => onFilterChange('newAccount', v)}
              />
            </th>
            <th>
              <select
                aria-label="Filter by rank"
                value={filters.rank}
                onChange={(e) => onFilterChange('rank', e.target.value)}
              >
                <option value="">All</option>
                {ranks.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </th>
            <th>
              <YesNoFilter
                label="potential conflict"
                value={filters.conflict}
                onChange={(v) => onFilterChange('conflict', v)}
              />
            </th>
            <th>
              <YesNoFilter
                label="tax certificate"
                value={filters.certificate}
                onChange={(v) => onFilterChange('certificate', v)}
              />
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
              <input
                type="search"
                placeholder="Search…"
                aria-label="Filter by special instruction"
                value={filters.specialInstructions}
                onChange={(e) => onFilterChange('specialInstructions', e.target.value)}
              />
            </th>
            {/* Decision: no filter here — the toolbar chips above already
                filter by status, server-side. */}
            <th aria-hidden="true" />
          </tr>
        </thead>
        <tbody>
          {!orders.length && (
            <tr>
              <td className="admin-empty-row" colSpan={11}>
                {allOrders.length ? 'No orders match these filters.' : 'No orders yet.'}
              </td>
            </tr>
          )}
          {orders.map((o) => (
            <tr key={o.id}>
              <td>{new Date(o.createdAt).toLocaleString()}</td>
              <td title={o.id}>
                <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                  <code>{o.shortId}</code>
                </a>
              </td>
              <td>{o.accountName || <span className="unknown">—</span>}</td>
              <td>{o.salesTerritory || <span className="unknown">—</span>}</td>
              {/* New account = Yes stacks a "Create account" action (or the
                  "Created ✓" state) beneath it, like the tax-cert cell. */}
              <td className={o.isNewAccount && !o.sfAccountId ? 'flag-yellow' : 'flag-green'}>
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
                {o.rank ? o.rank.split(' - ')[0] : <span className="unknown">—</span>}
              </td>
              <td className={o.hasConflict ? 'flag-yellow' : 'flag-green'}>
                {o.hasConflict ? (
                  <div className="cert-missing">
                    <span>Yes</span>
                    {o.conflictEmailSent || sentConflict.has(o.id) ? (
                      <span className="sf-created">Email Sent ✓ waiting for the response</span>
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
              <td className={o.hasCertificate ? 'flag-green' : o.isNewAccount ? 'flag-yellow' : undefined}>
                {o.hasCertificate ? (
                  <a href={certUrl(o.id)} target="_blank" rel="noreferrer">
                    Open
                  </a>
                ) : o.isNewAccount ? (
                  /* new account, no cert uploaded → show No + offer to request one */
                  <div className="cert-missing">
                    <span>No</span>
                    {o.taxCertEmailSent || sentTaxCert.has(o.id) ? (
                      <span className="sf-created">Email Sent ✓ waiting for the response</span>
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
              <td className="notes-cell" title={o.specialInstructions || ''}>
                {o.specialInstructions || <span className="unknown">—</span>}
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
                      <a
                        className="sf-created"
                        href={`${SF_INSTANCE_URL}/${o.sfOrderId}`}
                        target="_blank"
                        rel="noreferrer"
                        title={`Open ${o.sfOrderId} in Salesforce`}
                      >
                        {o.sfOrderNumber}
                      </a>
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
