export default function OrderHeader({
  seasons,
  season,
  onSeasonChange,
  form,
  setField,
  totalAmount,
  shipWindows = [],
}) {
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

        {form.representativeOk === false && (
          <fieldset className="inline-radios">
            <legend>
              Is this your first order? <span className="req">*</span>
            </legend>
            <label>
              <input
                type="radio"
                name="firstOrder"
                checked={form.firstOrder === true}
                onChange={() => setField('firstOrder', true)}
              />
              Yes
            </label>
            <label>
              <input
                type="radio"
                name="firstOrder"
                checked={form.firstOrder === false}
                onChange={() => setField('firstOrder', false)}
              />
              No
            </label>
          </fieldset>
        )}

        <label>
          Ship Window
          <select
            value={form.shipWindow}
            onChange={(e) => setField('shipWindow', e.target.value)}
            disabled={!season}
          >
            <option value="">
              {!season
                ? 'Select a collection first…'
                : shipWindows.length
                  ? 'Select a ship window…'
                  : 'No ship windows for this collection'}
            </option>
            {shipWindows.map((w) => (
              <option key={w} value={w}>
                {w}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="ship-window-note">Please allow 7–12 days for transit.</p>
    </section>
  )
}
