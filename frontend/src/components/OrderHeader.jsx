// Rolling calendar-month ship windows starting this month, e.g. "07/01 - 07/31  2026".
function shipWindows(count = 12) {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return Array.from({ length: count }, (_, i) => {
    const start = new Date(now.getFullYear(), now.getMonth() + i, 1)
    const end = new Date(now.getFullYear(), now.getMonth() + i + 1, 0) // last day of the month
    const mm = pad(start.getMonth() + 1)
    const label = `${mm}/${pad(start.getDate())} - ${mm}/${pad(end.getDate())}  ${start.getFullYear()}`
    return { value: label, label }
  })
}

export default function OrderHeader({ seasons, season, onSeasonChange, form, setField, totalAmount }) {
  const windows = shipWindows()
  return (
    <section className="section order-header">
      <div className="brand">
        <h1>WOODEN SHIPS</h1>
        <div className="subtitle">Wholesale Order Form</div>
      </div>

      <div className="header-grid">
        <label>
          Collection / Season
          <select value={season} onChange={(e) => onSeasonChange(e.target.value)} required>
            <option value="">Select a collection…</option>
            {seasons.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Order date
          <input type="date" value={form.orderDate} onChange={(e) => setField('orderDate', e.target.value)} />
        </label>

        <div className="field">
          <span className="field-label">Order total</span>
          <span className="order-total">
            ${totalAmount.toFixed(2)}
          </span>
        </div>

        <fieldset className="inline-radios">
          <legend>
            Filled by <span className="req">*</span>
          </legend>
          <label>
            <input
              type="radio"
              name="representative"
              checked={form.representativeOk === true}
              onChange={() => setField('representativeOk', true)}
            />
            Sales Representative
          </label>
          <label>
            <input
              type="radio"
              name="representative"
              checked={form.representativeOk === false}
              onChange={() => setField('representativeOk', false)}
            />
            Customer
          </label>
        </fieldset>
        <label>
          Ship Window
          <select value={form.shipWindow} onChange={(e) => setField('shipWindow', e.target.value)}>
            <option value="">Select a ship window…</option>
            {windows.map((w) => (
              <option key={w.value} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="ship-window-note">Please allow 7–12 days for transit.</p>
    </section>
  )
}
