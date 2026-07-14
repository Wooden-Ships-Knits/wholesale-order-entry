function Field({ label, value, onChange, type = 'text', required = false, autoComplete }) {
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
      />
    </label>
  )
}

export default function Addresses({ billTo, shipTo, setBillTo, setShipTo }) {
  return (
    <section className="section addresses">
      <div className="address-col">
        <h2>Bill To</h2>
        <Field label="Buyer name" value={billTo.buyerName} onChange={(v) => setBillTo('buyerName', v)} />
        <Field label="Street" value={billTo.street} onChange={(v) => setBillTo('street', v)} />
        <Field label="City / State" value={billTo.cityState} onChange={(v) => setBillTo('cityState', v)} />
        <Field label="Zip" value={billTo.zip} onChange={(v) => setBillTo('zip', v)} />
        <Field label="Tel" value={billTo.tel} onChange={(v) => setBillTo('tel', v)} type="tel" />
        <Field label="Fax" value={billTo.fax} onChange={(v) => setBillTo('fax', v)} type="tel" />
      </div>
      <div className="address-col">
        <h2>Ship To</h2>
        <Field
          label="Email"
          value={shipTo.email}
          onChange={(v) => setShipTo('email', v)}
          type="email"
          required
          autoComplete="email"
        />
        <Field label="Street" value={shipTo.street} onChange={(v) => setShipTo('street', v)} />
        <Field label="City / State" value={shipTo.cityState} onChange={(v) => setShipTo('cityState', v)} />
        <Field label="Zip" value={shipTo.zip} onChange={(v) => setShipTo('zip', v)} />
        <Field label="Resale tax ID" value={shipTo.resaleTaxId} onChange={(v) => setShipTo('resaleTaxId', v)} />
      </div>
    </section>
  )
}
