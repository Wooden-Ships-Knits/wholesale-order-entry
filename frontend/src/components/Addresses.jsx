import { useEffect, useState } from 'react'
import AddressMap from './AddressMap'

function Field({ label, value, onChange, type = 'text', required = false, autoComplete, disabled = false }) {
  return (
    <label>
      {label}
      {required && <span className="req">*</span>}
      <input
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        autoComplete={autoComplete}
        disabled={disabled}
      />
    </label>
  )
}

export default function Addresses({ billTo, shipTo, setBillTo, setShipTo }) {
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
        <Field label="Buyer name" value={billTo.buyerName} onChange={(v) => setBillTo('buyerName', v)} />
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
          
        <Field label="Street" value={billTo.street} onChange={(v) => setBillTo('street', v)} />
        <Field label="City / State" value={billTo.cityState} onChange={(v) => setBillTo('cityState', v)} />
        <Field label="Zip" value={billTo.zip} onChange={(v) => setBillTo('zip', v)} />
        <Field label="Tel" value={billTo.tel} onChange={(v) => setBillTo('tel', v)} type="tel" />
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
