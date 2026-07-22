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
        <img src="/ws-logo-black.png" alt="Wooden Ships — Paola Buendia" className="brand-logo" />
      </div>

      <div className="header-grid">
        {/* Row 1: Filled by (left) · Order total (right) */}
        <fieldset className="inline-radios ha-filled">
          <legend>
            Filled by<span className="req">*</span>
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

        <div className="field ha-total">
          <span className="field-label">Order total</span>
          <span className="order-total">
            ${totalAmount.toFixed(2)}
          </span>
        </div>

        {/* Row 2: Order date · Collection · Ship window */}
        <label className="ha-date">
          Order date<span className="req">*</span>
          <input type="date" value={form.orderDate} onChange={(e) => setField('orderDate', e.target.value)} />
        </label>

        <label className="ha-season">
          Collection / Season<span className="req">*</span>
          <select value={season} onChange={(e) => onSeasonChange(e.target.value)} required>
            <option value="">Select a collection…</option>
            {seasons.map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} — {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="ha-ship">
          Ship Window<span className="req">*</span>
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

        {form.representativeOk === false && (
          <fieldset className="inline-radios">
            <legend>
              Is this your first order with Wooden Ships?<span className="req">*</span>
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
    </section>
  )
}
