import { useEffect, useMemo, useRef, useState } from 'react'
import {
  cancelSignatureLink,
  cardPdfUrl,
  certUrl,
  createSfAccount,
  getConflictEmail,
  getOrderShipWindows,
  getSignatureEmail,
  pdfUrl,
  setConflictResolution,
  setOrderAccount,
  setOrderShipWindow,
  setOrderStatus,
  suggestAccounts,
} from './api'
import { distinctValues, rankCode } from './filterOrders'
import EmailDraftModal from '../components/EmailDraftModal'

// Money for display only — the DB keeps numeric. Same format as the signing
// page so an amount reads identically wherever the team sees it.
const money = (n) =>
  (Number(n) || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' })

// Salesforce My Domain — the pushed order record opens at <instance>/<recordId>.
// Change this if the org's domain changes (e.g. a sandbox).
const SF_INSTANCE_URL = 'https://wooden-ships.my.salesforce.com'

// Always render Yes / No (never blank) — null/undefined is treated as No.
// `tone` tints the cell only when the answer is Yes (green/red as given).
function YesNoCell({ value, tone }) {
  const yes = Boolean(value)
  return <td className={yes ? `flag-${tone}` : undefined}>{yes ? 'Yes' : 'No'}</td>
}

/** The "New account" cell.
 *
 * Yes/No comes from `accountExists` — whether a Salesforce account with this
 * store name was found — not from the buyer's "is this your first order?"
 * answer. A store Salesforce has never heard of is new, whatever anyone ticked.
 *
 * "Created ✓" is keyed on sfAccountCreated, NOT sfAccountId: the id is also set
 * at submit time from the buyer's own lookup, so keying on it claimed
 * "Created ✓" for accounts nobody made and hid the button when it was needed.
 */
function NewAccountCell({ order: o, creating, onCreate }) {
  // Created here → always Yes / Created ✓, checked BEFORE the name lookup.
  // Creating the account puts the store in Salesforce, so the lookup would
  // then report "exists" and flip this row to No — erasing the fact that it
  // was a new account we made. This order was new; that doesn't change.
  if (o.sfAccountCreated) {
    return (
      <td className="flag-green">
        <div className="cert-missing">
          <span>Yes</span>
          <span className="sf-created" title={o.sfAccountId}>
            Created ✓
          </span>
        </div>
      </td>
    )
  }

  // accountExists null = lookup didn't run / failed. Fall back to the buyer's
  // answer, but say so — an unverified guess must not read as a verdict.
  const unverified = o.accountExists == null
  const isNew = unverified ? Boolean(o.isNewAccount) : !o.accountExists

  if (!isNew) return <td className="flag-green">No</td>

  return (
    <td className="flag-yellow">
      <div className="cert-missing">
        <span>Yes</span>
        {unverified && <span className="sub">unverified</span>}
        <button type="button" className="chip" disabled={creating} onClick={onCreate}>
          {creating ? 'Creating…' : 'Create account'}
        </button>
      </div>
    </td>
  )
}

/** Account name cell, editable while the order is still awaiting review.
 *
 * Reps can't always find the right store — a franchise has one account per
 * location and the lookup is an exact name match — so orders arrive linked to
 * the wrong account or to none. Correcting it here sets the Salesforce account
 * id as well as the name; without the id the Accept push has nothing to file
 * the order against.
 */
function AccountNameCell({ order: o, onChanged, onError }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(o.accountName || '')
  const [hits, setHits] = useState([])
  const [saving, setSaving] = useState(false)
  // Shown next to the buttons as well as in the page banner. The banner sits
  // above the table, and this cell is reached by scrolling down and across a
  // wide one — so a rejected save (a live signing link blocks a relink) looked
  // exactly like a dead button.
  const [failed, setFailed] = useState('')

  // Admin page is authenticated, so search-as-you-type is fine here (on the
  // public form it would expose the stockist list).
  useEffect(() => {
    if (!editing || text.trim().length < 2) {
      setHits([])
      return
    }
    const id = setTimeout(async () => {
      try {
        const { suggestions } = await suggestAccounts(text)
        setHits(suggestions)
      } catch {
        setHits([]) // a failed search shouldn't block typing a free-text name
      }
    }, 250)
    return () => clearTimeout(id)
  }, [editing, text])

  async function save(accountName, accountId) {
    setSaving(true)
    setFailed('')
    try {
      await setOrderAccount(o.id, accountName, accountId)
      setEditing(false)
      onChanged()
    } catch (err) {
      setFailed(err.message)
      onError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <td>
        <div className="cert-missing">
          <span>{o.accountName || <span className="unknown">—</span>}</span>
          {/* Once accepted the order is in Salesforce under a specific
              account; relinking here would only desync the two. */}
          {o.status === 'submitted' && (
            <button type="button" className="link-btn inline" onClick={() => setEditing(true)}>
              Change
            </button>
          )}
        </div>
      </td>
    )
  }

  return (
    <td>
      <div className="account-edit">
        <input
          type="text"
          value={text}
          autoFocus
          disabled={saving}
          placeholder="Store name"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Escape' && setEditing(false)}
        />
        {hits.length > 0 && (
          <ul className="account-hits">
            {hits.map((h) => (
              <li key={h.accountId}>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => save(h.name, h.accountId)}
                  title={[h.salesTerritory, h.rank].filter(Boolean).join(' · ')}
                >
                  <span className="suggestion-name">{h.name}</span>
                  <span className="suggestion-where">
                    {[h.cityState, h.salesTerritory].filter(Boolean).join(' · ')}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="account-edit-actions">
          {/* Saving without picking sends no id; the backend still resolves the
              typed name against Salesforce (names are unique) and only treats
              it as a new store when nothing matches. So this is just "Save". */}
          <button
            type="button"
            className="chip"
            disabled={saving || !text.trim()}
            onClick={() => save(text.trim(), null)}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="link-btn inline" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
        {failed && <p className="account-edit-error">{failed}</p>}
      </div>
    </td>
  )
}

/** Ship window cell, editable while the order is still awaiting review.
 *
 * Options are the live list for this order's own season, so a window that has
 * since sold out (struck through in the planning sheet) isn't offered. The
 * season itself is deliberately not editable — line prices and Salesforce
 * product ids were resolved from that season's price book at submit.
 */
function ShipWindowCell({ order: o, onChanged, onError }) {
  const [editing, setEditing] = useState(false)
  const [options, setOptions] = useState(null) // null = still loading
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!editing) return
    let stale = false
    getOrderShipWindows(o.id)
      .then((d) => !stale && setOptions(d.shipWindows || []))
      .catch((err) => {
        if (stale) return
        setOptions([])
        onError(err.message)
      })
    return () => {
      stale = true
    }
  }, [editing, o.id])

  async function save(value) {
    if (!value || value === o.shipWindow) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await setOrderShipWindow(o.id, value)
      setEditing(false)
      onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!editing) {
    return (
      <td>
        <div className="cert-missing">
          <span>{o.shipWindow || <span className="unknown">—</span>}</span>
          {o.status === 'submitted' && (
            <button type="button" className="link-btn inline" onClick={() => setEditing(true)}>
              Change
            </button>
          )}
        </div>
      </td>
    )
  }

  return (
    <td>
      <div className="cert-missing">
        <select
          autoFocus
          disabled={saving || options === null}
          defaultValue={o.shipWindow || ''}
          onChange={(e) => save(e.target.value)}
        >
          <option value="">{options === null ? 'Loading…' : 'Select a ship window…'}</option>
          {/* The current value may no longer be offered (window since closed);
              keep it listed so the dropdown doesn't silently blank it. */}
          {o.shipWindow && !(options || []).includes(o.shipWindow) && (
            <option value={o.shipWindow}>{o.shipWindow} (current)</option>
          )}
          {(options || []).map((w) => (
            <option key={w} value={w}>
              {w}
            </option>
          ))}
        </select>
        <button type="button" className="link-btn inline" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </div>
    </td>
  )
}

/** Payment cell: which Kugamon record type to pick, plus the card summary and
 *  a link to the admin copy showing the full number.
 *
 *  The number itself is never in this response — `Open card` fetches it from
 *  the encrypted copy, which is purged on Accept/Decline. */
function PaymentCell({ order: o }) {
  if (!o.paymentMethod) return <td><span className="unknown">—</span></td>

  const isCard = o.paymentMethod === 'Credit Card'
  return (
    <td>
      <div className="cert-missing">
        <span>{o.paymentMethod}</span>
        {isCard && (o.cardLast4 || o.cardExp) && (
          <span className="sub">
            {o.cardLast4 ? `•••• ${o.cardLast4}` : ''}
            {o.cardExp ? `  exp ${o.cardExp}` : ''}
          </span>
        )}
        {isCard && o.cardName && <span className="sub">{o.cardName}</span>}
        {isCard &&
          (o.hasCardCopy ? (
            <a className="chip" href={cardPdfUrl(o.id)} target="_blank" rel="noreferrer">
              Open card
            </a>
          ) : (
            <span className="sub">card purged</span>
          ))}
        {o.approvalBeforeCharge === true && <span className="sub">approval first</span>}
      </div>
    </td>
  )
}

// Buyer signature by emailed link. Three states, colour-coded so the column
// scans without reading:
//   green + empty — no signature needed; the form was signed on the spot
//   yellow        — link is out, still waiting on the buyer
//   green + name  — signed
// The email now goes out automatically at submit (orders._send_signature_request);
// this column confirms it happened and is where a resend or cancel is done.
function SignatureCell({ order: o, sent, drafting, cancelling, onDraft, onCancel }) {
  // Signed on the form, so there is nothing outstanding. Deliberately empty:
  // a "—" here would read as missing data rather than "not applicable".
  if (!o.signatureRequested) return <td className="flag-green" />

  if (o.signatureSignedAt) {
    // The buyer may have changed quantities before signing. Say so — otherwise
    // the rep's copy and the accepted order silently disagree.
    const edited =
      o.origTotalQty != null &&
      (o.origTotalQty !== o.totalQty || o.origTotalAmount !== o.totalAmount)
    return (
      <td className="flag-green">
        <div className="cert-missing">
          <span className="sf-created">Signed ✓</span>
          <span className="sub">{o.signatureName}</span>
          <span className="sub">
            {new Date(o.signatureSignedAt).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            })}
          </span>
          {edited && (
            <span
              className="sub sig-edited"
              title="The buyer changed the order before signing"
            >
              edited: {o.origTotalQty} → {o.totalQty} pcs
            </span>
          )}
        </div>
      </td>
    )
  }

  // Requested but unsigned — yellow until the buyer acts.
  return (
    <td className="flag-yellow">
      <div className="cert-missing">
        {o.signatureEmailSent || sent ? (
          <span className="sf-created">Email Sent ✓ waiting for signature</span>
        ) : o.signatureHeldForConflict ? (
          /* Deliberately unsent, waiting on the conflict inquiry. Distinct from
             the failure below: nobody should "send it manually" here — clearing
             the conflict releases it on its own. */
          <span className="sig-held" title="Clearing the conflict sends this automatically">
            Held — conflict outstanding
          </span>
        ) : (
          /* The token exists but the send failed (SMTP down at submit). Say so
             rather than showing a reassuring "sent" the buyer never received. */
          <span className="sig-unsent">Not sent — send it manually</span>
        )}
        {o.signatureEmail && <span className="sub">{o.signatureEmail}</span>}
        {/* Re-drafting reuses the same unexpired token server-side, so the
            first link stays the only working one. */}
        <button type="button" className="chip" disabled={drafting} onClick={onDraft}>
          {drafting ? 'Drafting…' : o.signatureEmailSent || sent ? 'Resend' : 'Send email'}
        </button>
        {/* While a link is live this order can't be accepted, relinked or have
            its ship window changed — the buyer could still rewrite the lines.
            Cancelling is how the team takes that back. */}
        {o.signatureLinkLive && (
          <button
            type="button"
            className="chip"
            disabled={cancelling}
            title="Revoke the buyer's link so this order can be worked on again"
            onClick={onCancel}
          >
            {cancelling ? 'Cancelling…' : 'Cancel link'}
          </button>
        )}
      </div>
    </td>
  )
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
  const [resolving, setResolving] = useState(null) // id of the order whose conflict is being resolved
  const [sentConflict, setSentConflict] = useState(() => new Set()) // orders whose conflict email was sent
  const [sentTaxCert, setSentTaxCert] = useState(() => new Set()) // orders whose tax-cert email was sent
  const [sentSignature, setSentSignature] = useState(() => new Set()) // orders whose signature link was sent
  const [draftingSignature, setDraftingSignature] = useState(null)
  const [cancellingSignature, setCancellingSignature] = useState(null)

  // Dropdown options come from the unfiltered rows: picking a territory must
  // not remove the other territories from the list you picked it from.
  const territories = useMemo(() => distinctValues(allOrders, (o) => o.salesTerritory), [allOrders])
  const writers = useMemo(() => distinctValues(allOrders, (o) => o.orderWrittenBy), [allOrders])
  const ranks = useMemo(() => distinctValues(allOrders, (o) => rankCode(o.rank)), [allOrders])
  const seasons = useMemo(() => distinctValues(allOrders, (o) => o.seasonCode), [allOrders])
  const shipWindows = useMemo(() => distinctValues(allOrders, (o) => o.shipWindow), [allOrders])

  // Footer totals over `orders` (the filtered rows), not `allOrders`: the
  // figure has to agree with the rows above it, or a filtered view shows a
  // total nobody can reconcile against what they can see.
  const totals = useMemo(
    () =>
      orders.reduce(
        (acc, o) => ({
          qty: acc.qty + (o.totalQty || 0),
          amount: acc.amount + (Number(o.totalAmount) || 0),
        }),
        { qty: 0, amount: 0 },
      ),
    [orders],
  )

  // Both header rows are sticky, so the filter row has to sit exactly at the
  // label row's height. That height isn't knowable in CSS — labels wrap
  // differently as column widths, zoom and the loaded font change — so measure
  // it and publish it as --admin-head-h. A ResizeObserver keeps it right when
  // the window resizes or a column grows.
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

  // Record how a conflict inquiry ended (cleared / real conflict) so the row
  // closes. A note is optional (prefilled when confirming an AI suggestion);
  // cancelling the prompt aborts without saving.
  async function resolveConflict(order, outcome, defaultNote = '') {
    const note = window.prompt(
      outcome === 'cleared'
        ? 'Mark CLEARED — safe to proceed. Optional note (e.g. what the rep said):'
        : 'Mark REAL CONFLICT. Optional note (e.g. what the rep said):',
      defaultNote,
    )
    if (note === null) return // cancelled
    setResolving(order.id)
    try {
      await setConflictResolution(order.id, outcome, note)
      onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setResolving(null)
    }
  }

  // Ask the buyer to review and sign. The server mints (or reuses) the signing
  // token while building this draft — the link can't exist without one.
  async function draftSignatureEmail(order) {
    setDraftingSignature(order.id)
    try {
      const d = await getSignatureEmail(order.id)
      // To the buyer, CC the territory's lead rep (same as the tax-cert
      // request) so the rep knows their order went out for signature. The CC
      // may arrive empty when the territory has no rep — editable in the modal.
      setDraft({
        ...d,
        cc: d.cc || order.repEmail || '',
        title: 'Signature request draft',
        signatureOrderId: order.id,
      })
    } catch (err) {
      onError(err.message)
    } finally {
      setDraftingSignature(null)
    }
  }

  // Revoke the buyer's link. Destructive from their side — their link dies
  // mid-review — so it asks first.
  async function cancelSignature(order) {
    const who = order.signatureEmail || 'the buyer'
    if (
      !window.confirm(
        `Cancel the signing link for ${order.accountName || 'this order'}?\n\n` +
          `${who} will no longer be able to open or sign it, and you'll be able to ` +
          `accept or edit this order again.`,
      )
    )
      return
    setCancellingSignature(order.id)
    try {
      await cancelSignatureLink(order.id)
      onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setCancellingSignature(null)
    }
  }

  function handleSent() {
    if (draft?.conflictOrderId) {
      setSentConflict((prev) => new Set(prev).add(draft.conflictOrderId))
    }
    if (draft?.taxCertOrderId) {
      setSentTaxCert((prev) => new Set(prev).add(draft.taxCertOrderId))
    }
    if (draft?.signatureOrderId) {
      setSentSignature((prev) => new Set(prev).add(draft.signatureOrderId))
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
      // Token lets the customer's reply (with the cert attached) correlate back
      // to this order even if it lands on the bare wholesale@ address — matches
      // the backend conflict-email format ([#<kind>-<id>]). See docs/reply-tracking.md.
      subject: `Tax Certificate Request - ${name} [#tax_cert-${order.id}]`,
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
          <tr ref={headRowRef}>
            <th>Date</th>
            <th>Order ID</th>
            <th>Signature</th>
            <th>Season</th>
            <th>Quantity</th>
            <th>Total Amount</th>
            <th>Shipping Window</th>
            <th>Account Name</th>
            <th>Written By</th>
            <th>Sales Territory</th>
            <th>New account</th>
            <th>Rank</th>
            <th>Potential conflict</th>
            <th>Tax certificate</th>
            <th>Payment</th>
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
            {/* Quantity and Total Amount have no filter: a free-text or range
                control over a number nobody searches by would cost a column of
                width for nothing. The header row still needs the cells to stay
                aligned — one per column, or everything to the right shifts. */}
            <th aria-hidden="true" />
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
              <select
                aria-label="Filter by payment method"
                value={filters.paymentMethod}
                onChange={(e) => onFilterChange('paymentMethod', e.target.value)}
              >
                <option value="">All</option>
                <option value="Credit Card">Credit Card</option>
                <option value="PayPal">PayPal</option>
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
              <td className="admin-empty-row" colSpan={18}>
                {allOrders.length ? 'No orders match these filters.' : 'No orders yet.'}
              </td>
            </tr>
          )}
          {orders.map((o) => (
            <tr key={o.id}>
              {/* Date over time, so the column stops forcing its width on the
                  whole table. Month name rather than 7/31 — the Jakarta and US
                  teams read a numeric date in opposite orders. Seconds dropped;
                  nobody reviews orders to the second. */}
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
              <td title={o.id}>
                <a href={pdfUrl(o.id)} target="_blank" rel="noreferrer">
                  <code>{o.shortId}</code>
                </a>
              </td>
              <SignatureCell
                order={o}
                sent={sentSignature.has(o.id)}
                drafting={draftingSignature === o.id}
                cancelling={cancellingSignature === o.id}
                onDraft={() => draftSignatureEmail(o)}
                onCancel={() => cancelSignature(o)}
              />
              {/* Season is read-only: prices and Salesforce product ids were
                  resolved from this season's price book when the order was
                  submitted, so changing it would misprice every line. */}
              <td>{o.seasonCode || <span className="unknown">—</span>}</td>
              {/* Total pieces as the order stands. A buyer who changed the
                  quantities at signing changed this too — the Signature cell
                  is where the before/after shows. */}
              <td className="num">{o.totalQty ?? <span className="unknown">—</span>}</td>
              {/* Order value at the prices in force when it was submitted. Like
                  Quantity, a buyer who edited at signing changed this too. */}
              <td className="num">
                {o.totalAmount == null ? <span className="unknown">—</span> : money(o.totalAmount)}
              </td>
              <ShipWindowCell order={o} onChanged={onChanged} onError={onError} />
              <AccountNameCell order={o} onChanged={onChanged} onError={onError} />
              {/* Internal Use "Order written by" — only rep-filled orders carry
                  one, so a dash here means the customer submitted it. */}
              <td>{o.orderWrittenBy || <span className="unknown">—</span>}</td>
              {/* Flagged when empty: a territory-less order has no rep to fall
                  back to, so a customer-filled one sends its copy to the buyer
                  alone. Someone has to link it to the right account. */}
              <td className={o.salesTerritory?.trim() ? undefined : 'flag-yellow'}>
                {o.salesTerritory || <span className="unknown">—</span>}
              </td>
              {/* New account: answered by the submit-time Salesforce check, not
                  by the buyer's "first order" answer. Yes stacks a "Create
                  account" action (or "Created ✓") beneath it. */}
              <NewAccountCell
                order={o}
                creating={creating === o.id}
                onCreate={() => createAccount(o)}
              />
              {/* Conflict + its email action combined into one cell.
                  No conflict (or not yet checked) shows "No" — never blank. */}
               <td>
                {o.rank ? o.rank.split(' - ')[0] : <span className="unknown">—</span>}
              </td>
              {/* Conflict cell. Once resolved, the outcome tints the cell
                  (green cleared / red real-conflict) and the note is on hover. */}
              <td
                className={
                  o.conflictResolution === 'cleared'
                    ? 'flag-green'
                    : o.conflictResolution === 'real_conflict'
                      ? 'flag-red'
                      : o.hasConflict
                        ? 'flag-yellow'
                        : 'flag-green'
                }
              >
                {o.hasConflict ? (
                  o.conflictResolution ? (
                    <span className="sf-created" title={o.conflictResolutionNote || ''}>
                      {o.conflictResolution === 'cleared'
                        ? 'Resolved ✓ Cleared'
                        : 'Resolved ✓ Real conflict'}
                    </span>
                  ) : (
                    <div className="cert-missing">
                      <span>Yes</span>
                      {o.conflictEmailSent || sentConflict.has(o.id) ? (
                        <>
                          <span className="sf-created">Email Sent ✓ waiting for the response</span>
                          {/* AI suggestion from a captured rep reply. A proposal
                              only — Confirm records it (note prefilled with the
                              reason). "unclear" shows nothing. */}
                          {o.conflictAiOutcome && o.conflictAiOutcome !== 'unclear' && (
                            <div className="ai-suggest" title={o.conflictAiReason || ''}>
                              <span>
                                AI: {o.conflictAiOutcome === 'cleared' ? 'Cleared' : 'Real conflict'}
                                {o.conflictAiConfidence != null
                                  ? ` (${Math.round(o.conflictAiConfidence * 100)}%)`
                                  : ''}
                              </span>
                              <button
                                type="button"
                                className="chip"
                                disabled={resolving === o.id}
                                onClick={() =>
                                  resolveConflict(o, o.conflictAiOutcome, o.conflictAiReason || '')
                                }
                              >
                                Confirm
                              </button>
                            </div>
                          )}
                          <div className="decide">
                            <button
                              type="button"
                              className="chip"
                              disabled={resolving === o.id}
                              onClick={() => resolveConflict(o, 'cleared')}
                            >
                              Cleared
                            </button>
                            <button
                              type="button"
                              className="chip"
                              disabled={resolving === o.id}
                              onClick={() => resolveConflict(o, 'real_conflict')}
                            >
                              Real conflict
                            </button>
                          </div>
                        </>
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
                  )
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
              <PaymentCell order={o} />
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
        {/* Totals for the rows on screen — so the figure always matches what
            the filters are showing rather than the whole table. Rendered only
            when there is something to add up; a footer reading $0.00 under an
            empty result reads as a real total of zero. */}
        {orders.length > 0 && (
          <tfoot>
            <tr>
              <td className="totals-label" colSpan={4}>
                Total — {orders.length} order{orders.length === 1 ? '' : 's'}
              </td>
              <td className="num">{totals.qty}</td>
              <td className="num">{money(totals.amount)}</td>
              <td colSpan={12} />
            </tr>
          </tfoot>
        )}
      </table>
    </>
  )
}
