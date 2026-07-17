import { useEffect, useMemo, useRef, useState } from 'react'
import { getSeasons, getReps, getOrderWriters, getShipWindows, getProducts, getNearbyAccounts, submitOrder } from './api'
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
    firstOrder: null,
    sfAccountId: null,
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
  const [terms, setTermsState] = useState({ signatureName: '', signatureDate: today(), accepted: false })
  const [internal, setInternalState] = useState({
    newOrReorder: '',
    accountStatus: '',
    campaign: '',
    campaignOther: '',
    poNumber: '',
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
    setForm((p) => ({ ...p, sfAccountId: m.accountId }))
    setBillToState({
      buyerName: m.name || '',
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

  const { totalPieces, totalAmount, perLine } = useMemo(() => computeTotals(resolved), [resolved])
  const minimums = useMemo(() => validateMinimums(resolved), [resolved])

  async function onSubmit(e) {
    e.preventDefault()
    const problems = [...minimums.errors]
    if (totalPieces === 0) problems.unshift('No items entered yet.')
    if (form.representativeOk === null) problems.push('Please select who is filling in this form.')
    if (form.representativeOk === false && form.firstOrder === null)
      problems.push('Please tell us whether this is your first order.')
    if (!shipTo.email) problems.push('Ship To email is required.')
    if (!terms.signatureName) problems.push('Signature is required.')
    if (!terms.accepted) problems.push('You must accept the terms & conditions.')
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
      sfAccountId: form.sfAccountId,
      billTo,
      shipTo,
      payment,
      taxExemption: {
        repNotified: tax.repNotified,
        sendingCert: tax.sendingCert,
        certOnFile,
        certFile: certFilePayload,
      },
      terms,
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
      
      <BuyerLookup onSelect={applyAccount} onResult={(m) => setLookupNoMatch(m.length === 0)} />
      <Addresses billTo={billTo} shipTo={shipTo} setBillTo={setBillTo} setShipTo={setShipTo} />

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
      <TermsSignature terms={terms} setTerms={setTerms} />

      {conflictResult && (
        <ConflictWarning result={conflictResult} onDismiss={() => setConflictResult(null)} />
      )}

      {submitNotice && <p className="submit-notice">{submitNotice}</p>}
      <div className="submit-row">
        <button type="submit" className="submit-btn" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit order'}
        </button>
      </div>

      <Footer />
    </form>
  )
}
