// /sign/<token> — the buyer reviews their order, may adjust quantities, and
// signs. Reached from the emailed link; there is no login.
//
// Reuses ProductLines and validation.js unchanged, so the grid, the minimum
// rules and the error wording are literally the same code the order form runs.
// The server re-prices and re-validates everything anyway (routers/sign.py) —
// this is the mirror, not the authority.
import { useEffect, useMemo, useRef, useState } from 'react'
import { getOrderToSign, getProducts, getShipWindows, saveDraft, signOrder } from '../api'
import { catalogKey, computeTotals, validateMinimums } from '../validation'
import Addresses from '../components/Addresses'
import Notes from '../components/Notes'
import Payment from '../components/Payment'
import ProductLines from '../components/ProductLines'

const money = (n) =>
  (n || 0).toLocaleString('en-US', { style: 'currency', currency: 'USD' })

let lineSeq = 0
// Saved order lines -> the shape ProductLines works with. `query` seeds the
// style typeahead so an existing line shows its name rather than an empty box.
const lineFromItem = (i) => ({
  id: ++lineSeq,
  query: i.styleName,
  styleName: i.styleName,
  color: i.color,
  qty: { xs: i.qtyXs || 0, sm: i.qtySm || 0, ml: i.qtyMl || 0 },
})
const makeLine = () => ({ id: ++lineSeq, query: '', styleName: '', color: '', qty: {} })

export default function SignPage({ token }) {
  const [order, setOrder] = useState(null)
  const [rows, setRows] = useState([])
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [loadError, setLoadError] = useState('')
  // Editable copies of the order, seeded once the GET lands. Same shapes the
  // order form uses so Addresses / Payment / Notes drop straight in.
  const [billTo, setBillToState] = useState(null)
  const [shipTo, setShipToState] = useState(null)
  const [orderDate, setOrderDate] = useState('')
  const [shipWindow, setShipWindow] = useState('')
  const [shipWindows, setShipWindows] = useState([])
  const [poNumber, setPoNumber] = useState('')
  const [notes, setNotes] = useState('')
  // Card number is NEVER prefilled — it isn't stored (rule 1). The buyer keeps
  // the card on file unless they tick "use a different card", which reveals
  // empty fields rather than pretending we know the number.
  const [payment, setPaymentState] = useState({
    method: '', approvalBeforeCharge: null, cardNumber: '', cardName: '', expDate: '', cvv: '',
  })
  const [replaceCard, setReplaceCard] = useState(false)

  const [signatureName, setSignatureName] = useState('')
  const [savingDraft, setSavingDraft] = useState(false)
  // When the buyer last pressed Save draft, seeded from the order so a
  // returning buyer is told their work is here rather than guessing.
  const [draftSavedAt, setDraftSavedAt] = useState(null)
  // Anything typed since the last save. Drives both the button's wording and
  // the tab-close warning — without it, a buyer who closes the tab loses work
  // they reasonably assumed a Save button had protected.
  const [dirty, setDirty] = useState(false)
  const [accepted, setAccepted] = useState(false)
  // Mirrors the order form's second acknowledgement. Client-side only, like on
  // the form: the backend has no info_confirmed field, it gates submission.
  const [confirmed, setConfirmed] = useState(false)
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(null)

  // Mark the form dirty on any real edit. A ref counter rather than a flag on
  // `order`: the load below sets a dozen pieces of state in one batch, so the
  // first run of this effect after loading IS that batch, not the buyer typing.
  // Skipping exactly that run is what stops a freshly opened page claiming
  // unsaved changes.
  const hydrationRuns = useRef(0)
  useEffect(() => {
    if (!order) return
    if (hydrationRuns.current === 0) {
      hydrationRuns.current = 1
      return
    }
    setDirty(true)
  }, [order, lines, billTo, shipTo, orderDate, shipWindow, poNumber, notes, payment, replaceCard])

  // A Save button implies work is safe; without this a buyer who closes the
  // tab after typing loses everything since their last save with no warning.
  // Suppressed once signed — leaving a finished order is not a mistake.
  useEffect(() => {
    if (!dirty || done) return
    const warn = (e) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, done])

  useEffect(() => {
    let cancelled = false
    getOrderToSign(token)
      .then((data) => {
        if (cancelled) return
        setOrder(data)
        setDraftSavedAt(data.draftSavedAt || null)
        setLines(data.items.length ? data.items.map(lineFromItem) : [makeLine()])
        setBillToState({ ...data.billTo })
        setShipToState({ ...data.shipTo })
        setOrderDate(data.orderDate || '')
        setShipWindow(data.shipWindow || '')
        setPoNumber(data.poNumber || '')
        setNotes(data.notes || '')
        setPaymentState((p) => ({
          ...p,
          method: data.payment.method || '',
          approvalBeforeCharge: data.payment.approvalBeforeCharge,
          cardName: data.payment.cardName || '',
          expDate: data.payment.cardExp || '',
        }))
        // Ship windows for this season, so the buyer picks from the live list
        // rather than typing something the team can't ship to.
        getShipWindows(data.season)
          .then((d) => !cancelled && setShipWindows(d.shipWindows))
          .catch(() => !cancelled && setShipWindows([]))
        // The catalog is what makes the lines editable — without it every line
        // stays unmatched and the totals read zero.
        setLoadingProducts(true)
        return getProducts(data.season)
          .then((d) => !cancelled && setRows(d.rows))
          .catch((e) => !cancelled && setLoadError(`Could not load products: ${e.message}`))
          .finally(() => !cancelled && setLoadingProducts(false))
      })
      .catch((e) => !cancelled && setLoadError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [token])

  const catalog = useMemo(() => {
    const m = new Map()
    for (const r of rows) m.set(catalogKey(r.styleName, r.color), r)
    return m
  }, [rows])

  const resolved = useMemo(
    () =>
      lines.map((l) => ({
        ...l,
        row: l.styleName && l.color ? catalog.get(catalogKey(l.styleName, l.color)) || null : null,
      })),
    [lines, catalog],
  )

  const { totalPieces, totalAmount, perLine } = useMemo(
    () => computeTotals(resolved),
    [resolved],
  )
  const minimums = useMemo(() => validateMinimums(resolved), [resolved])

  const updateLine = (id, patch) =>
    setLines((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  const addLine = () => setLines((prev) => [...prev, makeLine()])
  const removeLine = (id) =>
    setLines((prev) =>
      prev.length > 1 ? prev.filter((l) => l.id !== id) : prev.map(() => makeLine()),
    )

  /** Everything the buyer may change, in the shape both endpoints accept. */
  function buildPayload() {
    const items = resolved
      .filter((l) => l.row && (perLine[l.id]?.pieces || 0) > 0)
      .map((l) => ({
        styleName: l.row.styleName,
        color: l.row.color,
        qtyXs: l.qty.xs || 0,
        qtySm: l.qty.sm || 0,
        qtyMl: l.qty.ml || 0,
      }))
    return {
      items,
      billTo,
      shipTo,
      orderDate: orderDate || null,
      shipWindow,
      poNumber,
      notes,
      // Card fields only travel when the buyer actually replaced the card;
      // otherwise we send the metadata and the stored card stands.
      payment: replaceCard ? payment : { ...payment, cardNumber: '', cvv: '' },
    }
  }

  /** Save without signing. Deliberately runs NO minimum checks — a half-built
   *  order is the normal state part-way through, and refusing to keep it is
   *  exactly what this button exists to prevent. Signing still enforces. */
  async function handleSaveDraft() {
    setNotice('')
    setSavingDraft(true)
    try {
      const res = await saveDraft(token, buildPayload())
      setDraftSavedAt(res.draftSavedAt || new Date().toISOString())
      setDirty(false)
      setNotice('Draft saved. You can close this page and come back to the same link.')
    } catch (err) {
      setNotice(err.message)
    } finally {
      setSavingDraft(false)
    }
  }

  async function handleSign(e) {
    e.preventDefault()
    setNotice('')

    const problems = []
    if (!signatureName.trim()) problems.push('Please type your full name to sign.')
    if (!accepted) problems.push('Please accept the Order Policies.')
    if (!confirmed) problems.push('Please confirm the order information is correct.')
    problems.push(...minimums.errors)
    if (problems.length) {
      setNotice(problems.join(' '))
      return
    }

    setSubmitting(true)
    try {
      const res = await signOrder(token, {
        signatureName: signatureName.trim(),
        ...buildPayload(),
      })
      setDone(res)
      setDirty(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setNotice(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <main className="sign-page">
        <p>Loading your order…</p>
      </main>
    )
  }

  // A dead link is the most likely way a buyer arrives here in error, so it
  // gets a real explanation instead of a bare error string.
  if (!order) {
    return (
      <main className="sign-page">
        <div className="sign-card">
          <h1>This link isn't valid</h1>
          <p>{loadError}</p>
          <p className="sign-note">
            Signing links stop working once the order has been signed, and expire after a
            couple of weeks. Reply to the email we sent you and we'll issue a new one.
          </p>
        </div>
      </main>
    )
  }

  if (done) {
    return (
      <main className="sign-page">
        <div className="sign-card">
          <h1>Thank you — your order is signed</h1>
          <p>
            Order <strong>{done.orderId}</strong> · {done.totalQty} pieces ·{' '}
            {money(done.totalAmount)}
          </p>
          <p className="sign-note">
            We've let the Wooden Ships team know. This is a record of what you signed, not a
            confirmation — we'll be in touch once your order has been reviewed. You can close
            this page; the link won't open again.
          </p>
        </div>
      </main>
    )
  }

  // Already signed, reached through a still-live link (rare, but a buyer who
  // signs in one tab and reloads another must not be shown a second form).
  if (order.signed) {
    return (
      <main className="sign-page">
        <div className="sign-card">
          <h1>This order is already signed</h1>
          <p className="sign-note">Nothing further is needed. We'll be in touch.</p>
        </div>
      </main>
    )
  }

  return (
    <main className="sign-page">
      <header className="sign-head">
        <h1>Review &amp; sign your order</h1>
        <p className="sign-sub">
          {order.accountName || order.buyerName} · {order.seasonLabel} · Ship window{' '}
          {order.shipWindow || '—'}
        </p>
      </header>

      {/* Order header. Store and season are read-only: reassigning the store
          is an admin action, and the season fixes the price book every line was
          costed against. Everything else here is the buyer's to correct. */}
      <section className="section">
        <div className="header-grid sign-header-grid">
          <div className="ha-filled">
            <span className="field-label">Account</span>
            <span className="sign-readonly">{order.accountName || order.buyerName || '—'}</span>
          </div>
          <label className="ha-po">
            PO # (optional)
            <input type="text" value={poNumber} onChange={(e) => setPoNumber(e.target.value)} />
          </label>
          <div className="ha-total">
            <span className="field-label">Order total</span>
            <span className="order-total">{money(totalAmount)}</span>
          </div>
          <label className="ha-date">
            Order date
            <input
              type="date"
              value={orderDate}
              onChange={(e) => setOrderDate(e.target.value)}
            />
          </label>
          <div className="ha-season">
            <span className="field-label">Collection / season</span>
            <span className="sign-readonly">{order.seasonLabel}</span>
          </div>
          <label className="ha-ship">
            Ship window
            <select value={shipWindow} onChange={(e) => setShipWindow(e.target.value)}>
              {/* The stored window may not be in the live list any more; keep
                  it as an option so opening the page can't silently change it. */}
              {shipWindow && !shipWindows.includes(shipWindow) && (
                <option value={shipWindow}>{shipWindow}</option>
              )}
              {shipWindows.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </label>
        </div>
        {order.shipWindowNote && <p className="ship-window-note">{order.shipWindowNote}</p>}
      </section>

      {billTo && shipTo && (
        <Addresses
          billTo={billTo}
          shipTo={shipTo}
          setBillTo={(k, v) => setBillToState((p) => ({ ...p, [k]: v }))}
          setShipTo={(k, v) => setShipToState((p) => ({ ...p, [k]: v }))}
          showLocationSearch
          isNewAccount={false}
        />
      )}

      {loadError && <div className="error-banner">{loadError}</div>}

      <ProductLines
        rows={rows}
        lines={resolved}
        updateLine={updateLine}
        addLine={addLine}
        removeLine={removeLine}
        perLine={perLine}
        totalPieces={totalPieces}
        totalAmount={totalAmount}
        badCells={minimums.badCells}
        loading={loadingProducts}
        seasonSelected
      />

      {/* Payment. The card on file is shown as its last 4 — the number itself
          is never stored, so it can't be prefilled. Ticking "use a different
          card" reveals the real fields; leaving it alone keeps the card the
          team already has. */}
      <section className="section">
        <h2>Payment</h2>
        <p className="sign-note" style={{ marginTop: 0 }}>
          {order.payment.cardLast4
            ? `On file: ${order.payment.method || 'Card'} ending •••• ${order.payment.cardLast4}${
                order.payment.cardExp ? `, expires ${order.payment.cardExp}` : ''
              }`
            : 'No card on file for this order.'}
        </p>
        <label className="check">
          <input
            type="checkbox"
            checked={replaceCard}
            onChange={(e) => {
              setReplaceCard(e.target.checked)
              // Never leave a half-typed number behind when it's hidden again.
              if (!e.target.checked) {
                setPaymentState((p) => ({ ...p, cardNumber: '', cvv: '' }))
              }
            }}
          />
          <span>Use a different card</span>
        </label>
        {replaceCard && (
          <Payment
            payment={payment}
            setPayment={(k, v) => setPaymentState((p) => ({ ...p, [k]: v }))}
          />
        )}
      </section>

      <Notes notes={notes} setNotes={setNotes} />

      {minimums.errors.length > 0 && (
        <div className="validation-panel">
          <strong>Please fix before signing:</strong>
          <ul>
            {minimums.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <form className="section terms" onSubmit={handleSign}>
        <h2>ORDER TERMS & CONDITIONS</h2>
        <div className="terms-text">
          <ul>
            <li>
              <strong>All Orders are Pre-Pay</strong>. Net Terms are not available. Payment is due right before shipping.
            </li>
            <li>
              All Wooden Ships are <strong>made to order</strong>.
            </li>
            <li>
              Changes to your order may be requested within{' '}
              <strong>10 days of order confirmation</strong>.
            </li>
            <li>
              Claims for shipping damage or shortages must be reported within{' '}
              <strong>10 days of receiving your order</strong>.
            </li>
            <li>
              Cancelled orders are subject to a <strong>15% restocking fee</strong>.
            </li>
            <li>
              Custom and special orders are <strong>final sale</strong> and are not eligible
              for cancellation, return, or refund once production has begun.
            </li>
          </ul>
          <p>
            All Orders are always Net Due prior to shipment. We do not offer net terms. Please
            let us know within 10 days if you do not agree to these terms. If we don't hear
            from you, we'll understand this as an acceptance of the terms and will proceed to
            purchase the yarn. Cancelled orders incur a 15% Restocking Fee.
          </p>
        </div>

        <label className="check">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
          />
          <span>
            I have read and accept the Order Terms & Conditions.<span className="req">*</span>
          </span>
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          <span>
            I confirm all the order information is correct.<span className="req">*</span>
          </span>
        </label>

        {/* No "email me a copy" checkbox: the copy always goes to the Ship To
            address above, editable in this form, with the rep CC'd. */}
        <p className="order-copy-note">
          A copy of this order form will be emailed to you and to your sales
          representative once you sign.
        </p>

        <label className="sign-signature">
          Your signature (type your full name)<span className="req">*</span>
          <input
            type="text"
            className="signature-input"
            value={signatureName}
            onChange={(e) => setSignatureName(e.target.value)}
            required
          />
        </label>

        {notice && <div className="error-banner">{notice}</div>}

        <div className="sign-actions">
          <button type="submit" className="submit-btn" disabled={submitting || savingDraft}>
            {submitting ? 'Signing…' : `Sign this order — ${totalPieces} pcs, ${money(totalAmount)}`}
          </button>
          {/* type="button" so it never triggers the form's submit handler —
              this is the one control that must NOT sign. */}
          <button
            type="button"
            className="draft-btn"
            onClick={handleSaveDraft}
            disabled={submitting || savingDraft}
          >
            {savingDraft ? 'Saving…' : 'Save draft'}
          </button>
        </div>
        <p className="sign-note draft-hint">
          Saving keeps your changes without signing — the same link will bring you
          back to them. Your card is only taken when you sign.
          {draftSavedAt && !dirty && (
            <> {' '}<strong>Draft saved {new Date(draftSavedAt).toLocaleString()}.</strong></>
          )}
        </p>
      </form>
    </main>
  )
}
