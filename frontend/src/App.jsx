import { useEffect, useMemo, useRef, useState } from 'react'
import { getSeasons, getReps, getOrderWriters, getShipWindows, getProducts, getNearbyAccounts, getTerritoryForState, submitOrder } from './api'
import { computeTotals, validateMinimums, catalogKey } from './validation'
import OrderHeader from './components/OrderHeader'
import BuyerLookup from './components/BuyerLookup'
import Addresses from './components/Addresses'
import ProductLines from './components/ProductLines'
import Payment from './components/Payment'
import TaxExemption from './components/TaxExemption'
import TermsSignature from './components/TermsSignature'
import InternalUse from './components/InternalUse'
import Notes from './components/Notes'
import ConflictWarning from './components/ConflictWarning'
import Footer from './components/Footer'

const today = () => new Date().toISOString().slice(0, 10)

const MAX_CERT_BYTES = 10 * 1024 * 1024 // keep in sync with backend CERT_MAX_BYTES

const fileToBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.onerror = () => reject(new Error('Could not read the certificate file.'))
    reader.readAsDataURL(file)
  })

let lineSeq = 0
const makeLine = () => ({ id: ++lineSeq, query: '', styleName: '', color: '', qty: {} })
const INITIAL_LINES = 3

// Pull the trailing 2-letter US state code out of a "City, ST" string (the
// \b keeps us from grabbing the last two letters of a plain word like "Canada").
const stateFromCityState = (cityState) => {
  const m = (cityState || '').match(/\b([A-Za-z]{2})\s*$/)
  return m ? m[1].toUpperCase() : ''
}

export default function App() {
  const [seasons, setSeasons] = useState([])
  const [reps, setReps] = useState([])
  const [writers, setWriters] = useState([])
  const [shipWindows, setShipWindows] = useState([])
  const [season, setSeason] = useState('')
  const [rows, setRows] = useState([])
  const [loadingProducts, setLoadingProducts] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [notes, setNotes] = useState('')

  const [lines, setLines] = useState(() => Array.from({ length: INITIAL_LINES }, makeLine))
  const [form, setForm] = useState({
    orderDate: today(),
    shipWindow: '',
    partShipOk: null,
    representativeOk: null,
    // Optional, and deliberately outside `internal`: since 2026-08-04 PO # sits
    // beside "Filled by" so a customer can supply one too.
    poNumber: '',
    firstOrder: null,
    accountName: '', // the store/account (distinct from the Bill To buyer person)
    sfAccountId: null,
    salesTerritory: null,
    specialInstructions: null,
    rank: null,
  })
  const [billTo, setBillToState] = useState({ buyerName: '', street: '', cityState: '', zip: '', tel: '', fax: '', lat: null, lng: null })
  const [shipTo, setShipToState] = useState({ email: '', street: '', cityState: '', zip: '', resaleTaxId: '', lat: null, lng: null })
  const [payment, setPaymentState] = useState({
    method: '',
    approvalBeforeCharge: null,
    cardNumber: '',
    cardName: '',
    expDate: '',
    cvv: '',
  })
  const [tax, setTaxState] = useState({ repNotified: false, sendingCert: false })
  const [certOnFile, setCertOnFile] = useState(false)
  const [certFile, setCertFile] = useState(null)
  const [lookupNoMatch, setLookupNoMatch] = useState(false)
  const [terms, setTermsState] = useState({ signatureName: '', signatureDate: today(), accepted: false, infoConfirmed: false, draftSignature: false, draftSignatureEmail: '' })
  const [internal, setInternalState] = useState({
    newOrReorder: '',
    accountStatus: '',
    campaign: '',
    campaignOther: '',
    rep: '',
    orderWrittenBy: '',
    split: null,
    splitWith: '',
  })
  const [submitNotice, setSubmitNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(null)

  useEffect(() => {
    getSeasons()
      .then((d) => setSeasons(d.seasons))
      .catch((e) => setLoadError(`Could not load collections: ${e.message}`))
    getReps()
      .then((d) => setReps(d.reps))
      .catch(() => setReps([]))
    getOrderWriters()
      .then((d) => setWriters(d.writers))
      .catch(() => setWriters([]))
  }, [])

  function onSeasonChange(code) {
    setSeason(code)
    setRows([])
    setLines(Array.from({ length: INITIAL_LINES }, makeLine))
    // Ship windows are per-season: clear the old list and selection.
    setShipWindows([])
    setField('shipWindow', '')
    if (!code) return
    getShipWindows(code)
      .then((d) => setShipWindows(d.shipWindows))
      .catch(() => setShipWindows([]))
    setLoadingProducts(true)
    setLoadError('')
    getProducts(code)
      .then((d) => setRows(d.rows))
      .catch((e) => setLoadError(`Could not load products: ${e.message}`))
      .finally(() => setLoadingProducts(false))
  }

  const catalog = useMemo(() => {
    const m = new Map()
    for (const r of rows) m.set(catalogKey(r.styleName, r.color), r)
    return m
  }, [rows])

  // lines resolved against the catalog (row = matched product or null)
  const resolved = useMemo(
    () =>
      lines.map((l) => ({
        ...l,
        row: l.styleName && l.color ? catalog.get(catalogKey(l.styleName, l.color)) || null : null,
      })),
    [lines, catalog],
  )

  const updateLine = (id, patch) =>
    setLines((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  const addLine = () => setLines((prev) => [...prev, makeLine()])
  const removeLine = (id) =>
    setLines((prev) => (prev.length > 1 ? prev.filter((l) => l.id !== id) : prev.map(() => makeLine())))

  const setField = (k, v) => setForm((p) => ({ ...p, [k]: v }))
  const setBillTo = (k, v) => setBillToState((p) => ({ ...p, [k]: v }))
  const setShipTo = (k, v) => setShipToState((p) => ({ ...p, [k]: v }))
  const setPayment = (k, v) => setPaymentState((p) => ({ ...p, [k]: v }))
  const setTax = (k, v) => setTaxState((p) => ({ ...p, [k]: v }))
  const setTerms = (k, v) => setTermsState((p) => ({ ...p, [k]: v }))
  const setInternal = (k, v) => setInternalState((p) => ({ ...p, [k]: v }))

  function applyAccount(m) {
    setForm((p) => ({
      ...p,
      accountName: m.name || '',
      sfAccountId: m.accountId,
      salesTerritory: m.salesTerritory || null,
      specialInstructions: m.specialInstructions || null,
      rank: m.rank || null,
    }))
    setBillToState({
      buyerName: '',
      street: m.billTo.street || '',
      cityState: m.billTo.cityState || '',
      zip: m.billTo.zip || '',
      tel: m.billTo.tel || '',
      fax: m.billTo.fax || '',
      lat: null,
      lng: null,
    })
    setShipToState({
      email: m.email || '',
      street: m.shipTo.street || '',
      cityState: m.shipTo.cityState || '',
      zip: m.shipTo.zip || '',
      resaleTaxId: m.resaleTaxId || '',
      lat: null,
      lng: null,
    })
    setCertOnFile(Boolean(m.certificateOnFile))
    if (m.rep) setInternalState((p) => ({ ...p, rep: m.rep }))
  }

  // Filled by a rep on the buyer's behalf. Drives how the order gets signed:
  // the rep supplies a buyer email and we send the order out for signature,
  // rather than the rep signing a box that isn't theirs to sign. Explicit
  // === true because null means "not answered yet", which is neither.
  const isRepFilled = form.representativeOk === true

  // Payment + tax exemption only apply to accounts we don't already have on
  // file. A customer answers "is this your first order?" directly; for a rep
  // it's the Internal Use radio, or a buyer lookup that found nothing.
  const isNewAccount =
    form.representativeOk === false
      ? form.firstOrder === true
      : internal.accountStatus === 'new' || lookupNoMatch

  // Stockist conflict check (docs/conflict-checker.md): when a rep marks the
  // account New and the Ship To store address has coordinates from the map
  // search, ask the backend whether an existing stockist is too close. Each
  // coordinate pair is checked once, so dismissing the warning doesn't bring
  // it back for the same address. Warning only — never blocks submission.
  const [conflictResult, setConflictResult] = useState(null)
  const checkedCoords = useRef(new Set())
  const shouldCheckConflict =
    form.representativeOk === true &&
    internal.accountStatus === 'new' &&
    shipTo.lat != null &&
    shipTo.lng != null
  useEffect(() => {
    if (!shouldCheckConflict) return
    const key = `${shipTo.lat},${shipTo.lng}`
    if (checkedCoords.current.has(key)) return
    checkedCoords.current.add(key)
    let stale = false
    getNearbyAccounts(shipTo.lat, shipTo.lng)
      .then((r) => {
        if (!stale && r.conflict) setConflictResult(r)
      })
      .catch((e) => console.error('Conflict check failed:', e))
    return () => {
      stale = true
    }
  }, [shouldCheckConflict, shipTo.lat, shipTo.lng])

  // Auto-assign a sales territory to a NEW account from its Ship To state:
  // take the 2-letter code out of "City, ST" and look it up in the region/rep
  // sheet. Existing (matched) accounts keep the SalesTerritory__c from lookup,
  // so this only runs when isNewAccount is true.
  const shipState = stateFromCityState(shipTo.cityState)
  const [territoryStatus, setTerritoryStatus] = useState('')
  useEffect(() => {
    if (!isNewAccount || !shipState) {
      setTerritoryStatus('')
      return
    }
    let stale = false
    getTerritoryForState(shipState)
      .then((r) => {
        if (stale) return
        setForm((p) => ({ ...p, salesTerritory: r.territory || null }))
        setTerritoryStatus(r.territory ? '' : `No sales territory is mapped for ${shipState}.`)
      })
      .catch(() => !stale && setTerritoryStatus(''))
    return () => {
      stale = true
    }
  }, [isNewAccount, shipState])

  const { totalPieces, totalAmount, perLine } = useMemo(() => computeTotals(resolved), [resolved])
  const minimums = useMemo(() => validateMinimums(resolved), [resolved])

  async function onSubmit(e) {
    e.preventDefault()
    const problems = [...minimums.errors]
    if (totalPieces === 0) problems.unshift('No items entered yet.')
    // Required order-header fields (marked * on the form).
    if (!season) problems.push('Please select a collection / season.')
    if (!form.accountName.trim()) problems.push('Account name is required.')
    if (!form.orderDate) problems.push('Order date is required.')
    if (!form.shipWindow) problems.push('Please select a ship window.')
    if (form.representativeOk === null) problems.push('Please select who is filling in this form.')
    if (form.representativeOk === false && form.firstOrder === null)
      problems.push('Please tell us whether this is your first order.')
    // Internal Use fields are only shown (and only required) for a rep.
    if (form.representativeOk === true) {
      if (!internal.newOrReorder) problems.push('Internal Use: choose New or reorder.')
      if (!internal.accountStatus) problems.push('Internal Use: choose New account or Existing.')
      if (!internal.campaign) problems.push('Internal Use: choose a Campaign.')
      if (!internal.orderWrittenBy) problems.push('Internal Use: select who the order was written by.')
    }
    if (!shipTo.email) problems.push('Ship To email is required.')
    if (!shipTo.resaleTaxId?.trim()) problems.push('Resale tax ID is required.')
    // How the order gets signed follows from who filled the form: a rep sends
    // it to the buyer at the Ship To address (already required above), a
    // customer signs on the spot. Mirrors routers/orders.py.
    if (!isRepFilled && !terms.signatureName) problems.push('Signature is required.')
    // Only the buyer accepts the policies. A rep-filled order carries no
    // acknowledgement here — the buyer gives it on the signing page, and that
    // is what sets terms_accepted. Mirrors routers/orders.py.
    if (!isRepFilled && !terms.accepted)
      problems.push('You must accept the Order Policies.')
    if (!isRepFilled && !terms.infoConfirmed)
      problems.push('Please confirm the order information is correct.')
    if (certFile && certFile.size > MAX_CERT_BYTES) {
      problems.push('The tax exemption certificate must be 10 MB or smaller.')
    }
    if (problems.length) {
      setSubmitNotice(problems.join(' '))
      return
    }

    // Attach the uploaded tax cert as base64 (backend re-validates type/size).
    let certFilePayload = null
    if (certFile) {
      try {
        certFilePayload = { name: certFile.name, contentBase64: await fileToBase64(certFile) }
      } catch (err) {
        setSubmitNotice(err.message)
        return
      }
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

    const payload = {
      season,
      orderDate: form.orderDate,
      partShipOk: form.partShipOk,
      shipWindow: form.shipWindow,
      filledBy: form.representativeOk === true ? 'rep' : form.representativeOk === false ? 'customer' : '',
      poNumber: form.poNumber,
      // Customer's own "is this your first order?" answer — the customer-side
      // equivalent of the rep's Internal Use "New account" radio.
      firstOrder: form.firstOrder,
      accountName: form.accountName,
      sfAccountId: form.sfAccountId,
      salesTerritory: form.salesTerritory,
      specialInstructions: form.specialInstructions,
      rank: form.rank,
      billTo,
      shipTo,
      payment,
      taxExemption: {
        repNotified: tax.repNotified,
        sendingCert: tax.sendingCert,
        certOnFile,
        certFile: certFilePayload,
      },
      // draftSignature/Email are derived, not stored: a rep-filled order always
      // goes to the buyer to sign, at the Ship To address. The backend branches
      // on draftSignature to mint the signing link and email it
      // (routers/orders.py). The order copy needs nothing here — it is sent to
      // the Ship To address unconditionally.
      terms: {
        ...terms,
        draftSignature: isRepFilled,
        draftSignatureEmail: isRepFilled ? shipTo.email : null,
      },
      internal,
      notes,
      items,
    }

    setSubmitting(true)
    setSubmitNotice('')
    try {
      const result = await submitOrder(payload)
      setSubmitted(result)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setSubmitNotice(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <main className="order-form confirmation">
        <h1>Thank you — your order has been received.</h1>
        <p>
          Order reference: <strong>{submitted.orderId}</strong>
        </p>
        <p>
          {submitted.totalQty} pieces · ${submitted.totalAmount.toFixed(2)}
        </p>
        <p className="muted">Our team will process your order and follow up by email.</p>
      </main>
    )
  }

  return (
    <form className="order-form" onSubmit={onSubmit} noValidate>
      <OrderHeader
        seasons={seasons}
        season={season}
        onSeasonChange={onSeasonChange}
        form={form}
        setField={setField}
        totalAmount={totalAmount}
        shipWindows={shipWindows}
      />
      {loadError && <p className="error-banner">{loadError}</p>}

      {form.representativeOk === true && (
        <InternalUse
          internal={internal}
          setInternal={setInternal}
          certOnFile={certOnFile}
          setCertOnFile={setCertOnFile}
          reps={reps}
          writers={writers}
        />
      )}
      
      <BuyerLookup
        onSelect={applyAccount}
        onResult={(m) => setLookupNoMatch(m.length === 0)}
        accountName={form.accountName}
        setAccountName={(v) => setField('accountName', v.toUpperCase())}
      />
      <Addresses
        billTo={billTo}
        shipTo={shipTo}
        setBillTo={setBillTo}
        setShipTo={setShipTo}
        // "Search a location" only for a new account — same rule as
        // isNewAccount, which also gates the conflict check, Payment, and Tax
        // Exemption (rep marking New / no lookup match, or a customer's first
        // order).
        showLocationSearch={isNewAccount}
        // New customers ship to their billing address most of the time, so
        // "Same as Bill To" defaults on for them (Ship To still editable).
        isNewAccount={isNewAccount}
      />

      {isNewAccount && (form.salesTerritory || territoryStatus) && (
        <section className="section territory-auto">
          <label>
            Sales territory <span className="muted">(auto-assigned from the Ship To state)</span>
            <input type="text" value={form.salesTerritory || ''} readOnly placeholder="—" />
          </label>
          {territoryStatus && <p className="field-warning">{territoryStatus}</p>}
        </section>
      )}

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
        seasonSelected={Boolean(season)}
      />

      {minimums.errors.length > 0 && (
        <div className="validation-panel">
          <strong>Please fix before submitting:</strong>
          <ul>
            {minimums.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {isNewAccount && <Payment payment={payment} setPayment={setPayment} />}
      {isNewAccount && <TaxExemption certFile={certFile} setCertFile={setCertFile} />}
      <Notes notes={notes} setNotes={setNotes} />
      {/* Customer-filled only. Everything in this section — the policies, the
          acknowledgements, the signature and the order copy — belongs to the
          buyer, and a rep-filled order goes to them to sign; they get the same
          choices on the signing page instead (frontend/src/sign/SignPage.jsx).
          Same gating style as InternalUse above, which is rep-only. */}
      {!isRepFilled && (
        <TermsSignature terms={terms} setTerms={setTerms} />
      )}

      {conflictResult && (
        <ConflictWarning result={conflictResult} onDismiss={() => setConflictResult(null)} />
      )}

      {submitNotice && <p className="submit-notice">{submitNotice}</p>}
      <div className="submit-row">
        {/* A rep isn't finishing the order, they're handing it to the buyer to
            sign — so the button says what actually happens next. Same submit
            either way; only the wording differs. */}
        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting
            ? isRepFilled
              ? 'Sending…'
              : 'Submitting…'
            : isRepFilled
              ? 'Send to customer for signature'
              : 'Submit order'}
        </button>
      </div>

      <Footer />
    </form>
  )
}
