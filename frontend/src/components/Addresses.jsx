import { useEffect, useRef, useState } from 'react'
import AddressMap from './AddressMap'
import BuyerContactPicker from './BuyerContactPicker'

// Format a US phone number progressively as the user types: keep only the
// first 10 digits and render them as "(423) 240-9340".
function formatPhone(raw) {
  const digits = (raw || '').replace(/\D/g, '').slice(0, 10)
  if (digits.length <= 3) return digits
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

// "ADAM SMITH" / "adam smith" -> "Adam Smith", applied when the field loses
// focus rather than per keystroke (rewriting mid-word fights the typist).
//
// A MIRROR of backend/app/schemas/order.py::title_case, which is the authority
// — the PDF, the emails and Salesforce all read the normalised value from the
// database. This exists so the form shows what those will show. Keep the two
// in step, including the rule that already-mixed-case words ("McDonald",
// "DuBois") are left exactly as typed.
function titleCase(value) {
  return (value || '')
    .trim()
    .split(/(\s+)/)
    .map((token) => {
      const letters = token.replace(/[^a-zA-Z]/g, '')
      if (!letters) return token
      if (letters !== letters.toUpperCase() && letters !== letters.toLowerCase()) return token
      return token.toLowerCase().replace(/(^|[-'’])([a-z])/g, (_, sep, c) => sep + c.toUpperCase())
    })
    .join('')
}

function Field({ label, value, onChange, type = 'text', required = false, autoComplete, disabled = false, placeholder, titleCaseOnBlur = false }) {
  const [warning, setWarning] = useState('')
  const handleChange = (e) => {
    if (type === 'tel') {
      // More than 10 digits means a country code / prefix was included; we keep
      // only the first 10, so warn about that immediately. Don't nag about a
      // too-short number while the user is still typing — that's checked on blur.
      const digits = (e.target.value || '').replace(/\D/g, '')
      setWarning(digits.length > 10 ? 'Enter 10 digits only — drop any leading country code or prefix (e.g. 1).' : '')
      onChange(formatPhone(e.target.value))
    } else {
      onChange(e.target.value)
    }
  }
  const handleBlur = (e) => {
    if (titleCaseOnBlur) {
      const tidied = titleCase(e.target.value)
      if (tidied !== e.target.value) onChange(tidied)
      return
    }
    if (type !== 'tel') return
    // On leaving the field, flag an incomplete number (1–9 digits). Empty is
    // handled by `required` instead, so this only complains about a half-typed
    // one rather than about an untouched field.
    const digits = (e.target.value || '').replace(/\D/g, '')
    if (digits.length > 0 && digits.length < 10) {
      setWarning('Phone number must be 10 digits.')
    } else if (digits.length === 10) {
      setWarning('')
    }
  }
  return (
    <label>
      {label}
      {required && <span className="req">*</span>}
      <input
        type={type}
        value={type === 'tel' ? formatPhone(value) : value || ''}
        onChange={handleChange}
        onBlur={type === 'tel' || titleCaseOnBlur ? handleBlur : undefined}
        required={required}
        autoComplete={autoComplete}
        disabled={disabled}
        placeholder={placeholder}
        inputMode={type === 'tel' ? 'numeric' : undefined}
      />
      {warning && <span className="field-warning">{warning}</span>}
    </label>
  )
}

export default function Addresses({ billTo, shipTo, setBillTo, setShipTo, showLocationSearch = false, isNewAccount = false, buyerContacts = [] }) {
  const [sameAsShipping, setSameAsShipping] = useState(false)

  const billHasAddress = Boolean(billTo.street || billTo.cityState || billTo.zip)

  // New customers usually bill to their shipping address, so default the box on
  // for them — but only while Bill To is still empty, so we never clobber an
  // address the user already typed (e.g. a rep marking the account New after
  // filling Bill To). Unticking sticks: once Bill To is populated this stops
  // re-checking. Existing accounts (lookup autofills both sides) are untouched.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current) return
    if (isNewAccount && !billHasAddress) {
      seededRef.current = true
      setSameAsShipping(true)
    }
    // billHasAddress guards the seed; setSameAsShipping is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNewAccount, billHasAddress])

  // While checked, mirror the shared address fields from Ship To — including
  // when shipping is autofilled from the account lookup after the box is ticked.
  useEffect(() => {
    if (!sameAsShipping) return
    setBillTo('street', shipTo.street)
    setBillTo('cityState', shipTo.cityState)
    setBillTo('zip', shipTo.zip)
    setBillTo('lat', shipTo.lat)
    setBillTo('lng', shipTo.lng)
    // setBillTo is intentionally omitted: it's re-created each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sameAsShipping, shipTo.street, shipTo.cityState, shipTo.zip, shipTo.lat, shipTo.lng])

  // Editing a mirrored Bill To field (typing, or a Bill To map search) breaks
  // the link so the manual value isn't overwritten by later Ship To changes.
  const setBillUnlink = (field, value) => {
    if (sameAsShipping) setSameAsShipping(false)
    setBillTo(field, value)
  }

  // Street / City / Zip stay hidden until the address is populated — by the
  // location search (new customer picks a place) or the account lookup
  // (existing account autofills). Any one of the three being present reveals
  // the block so it can be reviewed / edited.
  const shipHasAddress = Boolean(shipTo.street || shipTo.cityState || shipTo.zip)

  return (
    <section className="section addresses">
      <div className="address-col">
        <div className="col-head">
          <h2>Ship To</h2>
        </div>
        {/* One control for Buyer name, never two. Several contacts to choose
            between makes it a dropdown; otherwise it stays the free-text field,
            which is what a new account or a buyer Salesforce doesn't know needs.
            buyerContacts is empty for customers, so they always get the text
            field. */}
        {buyerContacts.length > 1 ? (
          <BuyerContactPicker
            contacts={buyerContacts}
            value={billTo.buyerName}
            onPick={(name) => setBillTo('buyerName', name)}
          />
        ) : (
          <Field
            label="Buyer name"
            value={billTo.buyerName}
            onChange={(v) => setBillTo('buyerName', v)}
            autoComplete="name"
            titleCaseOnBlur
            required
          />
        )}
        {showLocationSearch && (
          <AddressMap
            lat={shipTo.lat}
            lng={shipTo.lng}
            onPlaceSelect={(p) => {
              setShipTo('street', p.street)
              setShipTo('cityState', p.cityState)
              setShipTo('zip', p.zip)
              setShipTo('lat', p.lat)
              setShipTo('lng', p.lng)
            }}
          />
        )}

        {shipHasAddress && (
          <>
            <Field label="Street" value={shipTo.street} onChange={(v) => setShipTo('street', v)} required />
            <Field label="City / State" value={shipTo.cityState} onChange={(v) => setShipTo('cityState', v)} required />
            <Field label="Zip" value={shipTo.zip} onChange={(v) => setShipTo('zip', v)} required />
          </>
        )}
        <Field label="Tel" value={billTo.tel} onChange={(v) => setBillTo('tel', v)} type="tel" placeholder="Example: (423) 240-9340" required />
      </div>
      <div className="address-col">
        <div className="col-head">
          <h2>Bill To</h2>
          <label className="check">
            <input
              type="checkbox"
              checked={sameAsShipping}
              onChange={(e) => setSameAsShipping(e.target.checked)}
            />
            Same as Ship To
          </label>
        </div>
        <Field
          label="Email"
          value={shipTo.email}
          onChange={(v) => setShipTo('email', v)}
          type="email"
          required
          autoComplete="email"
        />
        {showLocationSearch && (
          <AddressMap
            lat={billTo.lat}
            lng={billTo.lng}
            onPlaceSelect={(p) => {
              // Searching a Bill To address is a manual choice — unlink so it
              // isn't overwritten by the Ship To mirror.
              if (sameAsShipping) setSameAsShipping(false)
              setBillTo('street', p.street)
              setBillTo('cityState', p.cityState)
              setBillTo('zip', p.zip)
              setBillTo('lat', p.lat)
              setBillTo('lng', p.lng)
            }}
          />
        )}

        {billHasAddress && (
          <>
            <Field
              label="Street"
              required
              value={billTo.street}
              onChange={(v) => setBillUnlink('street', v)}
            />
            <Field
              label="City / State"
              required
              value={billTo.cityState}
              onChange={(v) => setBillUnlink('cityState', v)}
            />
            <Field label="Zip" value={billTo.zip} onChange={(v) => setBillUnlink('zip', v)} required />
          </>
        )}
        <Field label="Resale tax ID" value={shipTo.resaleTaxId} onChange={(v) => setShipTo('resaleTaxId', v)} required />
      </div>
    </section>
  )
}
