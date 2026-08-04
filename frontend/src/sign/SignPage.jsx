// /sign/<token> — the buyer reviews their order, may adjust quantities, and
// signs. Reached from the emailed link; there is no login.
//
// Reuses ProductLines and validation.js unchanged, so the grid, the minimum
// rules and the error wording are literally the same code the order form runs.
// The server re-prices and re-validates everything anyway (routers/sign.py) —
// this is the mirror, not the authority.
import { useEffect, useMemo, useState } from 'react'
import { getOrderToSign, getProducts, signOrder } from '../api'
import { catalogKey, computeTotals, validateMinimums } from '../validation'
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
  const [signatureName, setSignatureName] = useState('')
  const [accepted, setAccepted] = useState(false)
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(null)

  useEffect(() => {
    let cancelled = false
    getOrderToSign(token)
      .then((data) => {
        if (cancelled) return
        setOrder(data)
        setLines(data.items.length ? data.items.map(lineFromItem) : [makeLine()])
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

  async function handleSign(e) {
    e.preventDefault()
    setNotice('')

    const problems = []
    if (!signatureName.trim()) problems.push('Please type your full name to sign.')
    if (!accepted) problems.push('Please accept the Order Policies.')
    problems.push(...minimums.errors)
    if (problems.length) {
      setNotice(problems.join(' '))
      return
    }

    const items = resolved
      .filter((l) => l.row && (perLine[l.id]?.pieces || 0) > 0)
      .map((l) => ({
        styleName: l.row.styleName,
        color: l.row.color,
        qtyXs: l.qty.xs || 0,
        qtySm: l.qty.sm || 0,
        qtyMl: l.qty.ml || 0,
      }))

    setSubmitting(true)
    try {
      const res = await signOrder(token, { signatureName: signatureName.trim(), items })
      setDone(res)
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

      <section className="section sign-summary">
        <div className="sign-summary-grid">
          <div>
            <h3>Bill to</h3>
            <p>
              {order.accountName}
              <br />
              {order.billTo.street}
              <br />
              {order.billTo.cityState} {order.billTo.zip}
              <br />
              {order.billTo.tel}
            </p>
          </div>
          <div>
            <h3>Ship to</h3>
            <p>
              {order.accountName}
              <br />
              {order.shipTo.street}
              <br />
              {order.shipTo.cityState} {order.shipTo.zip}
              <br />
              {order.shipTo.email}
            </p>
          </div>
          <div>
            <h3>Payment</h3>
            <p>
              {order.payment.method || '—'}
              {order.payment.cardLast4 ? (
                <>
                  <br />
                  •••• {order.payment.cardLast4}
                </>
              ) : null}
            </p>
          </div>
        </div>
        <p className="sign-note">
          If any of these details are wrong, reply to our email rather than signing — they
          can't be changed on this page.
        </p>
      </section>

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
        <h2>ORDER POLICIES</h2>
        <div className="terms-text">
          <ul>
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
            I have read and accept the Order Policies.<span className="req">*</span>
          </span>
        </label>

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

        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Signing…' : `Sign this order — ${totalPieces} pcs, ${money(totalAmount)}`}
        </button>
      </form>
    </main>
  )
}
