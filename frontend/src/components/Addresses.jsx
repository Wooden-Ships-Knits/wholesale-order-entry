import { useEffect, useState } from 'react'
import AddressMap from './AddressMap'

// Format a US phone number progressively as the user types: keep only the
// first 10 digits and render them as "(423) 240-9340".
function formatPhone(raw) {
  const digits = (raw || '').replace(/\D/g, '').slice(0, 10)
  if (digits.length <= 3) return digits
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

function Field({ label, value, onChange, type = 'text', required = false, autoComplete, disabled = false, placeholder }) {
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
    if (type !== 'tel') return
    // On leaving the field, flag an incomplete number (1–9 digits). Empty is
    // fine — the phone isn't required.
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
        onBlur={type === 'tel' ? handleBlur : undefined}
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

export default function Addresses({ billTo, shipTo, setBillTo, setShipTo, showLocationSearch = false }) {
  const [sameAsBilling, setSameAsBilling] = useState(false)

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

  return (
    <section className="section addresses">
      <div className="address-col">
        <div className="col-head">
          <h2>Bill To</h2>
        </div>
        <Field
          label="Buyer name"
          value={billTo.buyerName}
          onChange={(v) => setBillTo('buyerName', v)}
          autoComplete="name"
        />
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

        <Field label="Street" value={billTo.street} onChange={(v) => setBillTo('street', v)} />
        <Field label="City / State" value={billTo.cityState} onChange={(v) => setBillTo('cityState', v)} />
        <Field label="Zip" value={billTo.zip} onChange={(v) => setBillTo('zip', v)} />
        <Field label="Tel" value={billTo.tel} onChange={(v) => setBillTo('tel', v)} type="tel" placeholder="Example: (423) 240-9340" />
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
              setShipTo('street', p.street)
              setShipTo('cityState', p.cityState)
              setShipTo('zip', p.zip)
              setShipTo('lat', p.lat)
              setShipTo('lng', p.lng)
            }}
          />
        )}

        <Field
          label="Street"
          value={shipTo.street}
          onChange={(v) => setShipTo('street', v)}
          disabled={sameAsBilling}
        />
        <Field
          label="City / State"
          value={shipTo.cityState}
          onChange={(v) => setShipTo('cityState', v)}
          disabled={sameAsBilling}
        />
        <Field label="Zip" value={shipTo.zip} onChange={(v) => setShipTo('zip', v)} disabled={sameAsBilling} />
        <Field label="Resale tax ID" value={shipTo.resaleTaxId} onChange={(v) => setShipTo('resaleTaxId', v)} />
      </div>
    </section>
  )
}
