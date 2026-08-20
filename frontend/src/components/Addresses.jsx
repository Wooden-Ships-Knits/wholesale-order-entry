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

function Field({ label, value, onChange, type = 'text', required = false, autoComplete, disabled = false, placeholder, titleCaseOnBlur = false, list }) {
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
        // Attaches a <datalist> of suggestions without making the field a
        // dropdown: it stays free text, it just offers what we know.
        list={list}
      />
      {warning && <span className="field-warning">{warning}</span>}
    </label>
  )
}

const BUYER_CONTACTS_LIST_ID = 'buyer-contacts'

export default function Addresses({ billTo, shipTo, setBillTo, setShipTo, showLocationSearch = false, isNewAccount = false, buyerContacts = [] }) {
  const [sameAsBilling, setSameAsBilling] = useState(false)

  const shipHasAddress = Boolean(shipTo.street || shipTo.cityState || shipTo.zip)

  // New customers usually ship to their billing address, so default the box on
  // for them — but only while Ship To is still empty, so we never clobber an
  // address the user already typed (e.g. a rep marking the account New after
  // filling Ship To). Unticking sticks: once Ship To is populated this stops
  // re-checking. Existing accounts (lookup autofills both sides) are untouched.
  const seededRef = useRef(false)
  useEffect(() => {
    if (seededRef.current) return
    if (isNewAccount && !shipHasAddress) {
      seededRef.current = true
      setSameAsBilling(true)
    }
    // shipHasAddress guards the seed; setSameAsBilling is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNewAccount, shipHasAddress])

  // While checked, mirror the shared address fields from Bill To — including
  // when billing is autofilled from the account lookup after the box is ticked.
  useEffect(() => {
    if (!sameAsBilling) return
    setShipTo('street', billTo.street)
    setShipTo('cityState', billTo.cityState)
    setShipTo('zip', billTo.zip)
    // Coordinates too, so the conflict check works when the address was
    // searched in the Bill To box.
    setShipTo('lat', billTo.lat)
    setShipTo('lng', billTo.lng)
    // setShipTo is intentionally omitted: it's re-created each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sameAsBilling, billTo.street, billTo.cityState, billTo.zip, billTo.lat, billTo.lng])

  // Editing a mirrored Ship To field (typing, or a Ship To map search) breaks
  // the link so the manual value isn't overwritten by later Bill To changes.
  const setShipUnlink = (field, value) => {
    if (sameAsBilling) setSameAsBilling(false)
    setShipTo(field, value)
  }

  // Street / City / Zip stay hidden until the address is populated — by the
  // location search (new customer picks a place) or the account lookup
  // (existing account autofills). Any one of the three being present reveals
  // the block so it can be reviewed / edited.
  const billHasAddress = Boolean(billTo.street || billTo.cityState || billTo.zip)

  return (
    <section className="section addresses">
      <div className="address-col">
        <div className="col-head">
          <h2>Bill To</h2>
        </div>
        {/* One field, not two: the account's contacts hang off this input as a
            <datalist>, so a rep can type a name Salesforce has never heard of
            or pick a known one, in the same box. The hint only surfaces when
            there is actually a choice to make, and only for reps —
            buyerContacts is empty for customers. */}
        <Field
          label="Buyer name"
          value={billTo.buyerName}
          onChange={(v) => setBillTo('buyerName', v)}
          autoComplete="name"
          titleCaseOnBlur
          required
          list={buyerContacts.length > 1 ? BUYER_CONTACTS_LIST_ID : undefined}
          placeholder={
            buyerContacts.length > 1
              ? `Type a name, or pick from ${buyerContacts.length} contacts`
              : undefined
          }
        />
        <BuyerContactPicker id={BUYER_CONTACTS_LIST_ID} contacts={buyerContacts} />
        {showLocationSearch && (
          <AddressMap
            lat={billTo.lat}
            lng={billTo.lng}
            onPlaceSelect={(p) => {
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
            <Field label="Street" value={billTo.street} onChange={(v) => setBillTo('street', v)} required />
            <Field label="City / State" value={billTo.cityState} onChange={(v) => setBillTo('cityState', v)} required />
            <Field label="Zip" value={billTo.zip} onChange={(v) => setBillTo('zip', v)} required />
          </>
        )}
        <Field label="Tel" value={billTo.tel} onChange={(v) => setBillTo('tel', v)} type="tel" placeholder="Example: (423) 240-9340" required />
      </div>
      <div className="address-col">
        <div className="col-head">
          <h2>Ship To</h2>
          <label className="check">
            <input
              type="checkbox"
              checked={sameAsBilling}
              onChange={(e) => setSameAsBilling(e.target.checked)}
            />
            Same as Bill To
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
            lat={shipTo.lat}
            lng={shipTo.lng}
            onPlaceSelect={(p) => {
              // Searching a Ship To address is a manual choice — unlink so it
              // isn't overwritten by the Bill To mirror.
              if (sameAsBilling) setSameAsBilling(false)
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
            <Field
              label="Street"
              required
              value={shipTo.street}
              onChange={(v) => setShipUnlink('street', v)}
            />
            <Field
              label="City / State"
              required
              value={shipTo.cityState}
              onChange={(v) => setShipUnlink('cityState', v)}
            />
            <Field label="Zip" value={shipTo.zip} onChange={(v) => setShipUnlink('zip', v)} required />
          </>
        )}
        <Field label="Resale tax ID" value={shipTo.resaleTaxId} onChange={(v) => setShipTo('resaleTaxId', v)} required />
      </div>
    </section>
  )
}
