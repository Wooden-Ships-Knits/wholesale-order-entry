export default function OrderHeader({ seasons, season, onSeasonChange, form, setField, totalAmount }) {
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
          <legend>Part ship OK?</legend>
          <label>
            <input
              type="radio"
              name="partShip"
              checked={form.partShipOk === true}
              onChange={() => setField('partShipOk', true)}
            />
            Yes
          </label>
          <label>
            <input
              type="radio"
              name="partShip"
              checked={form.partShipOk === false}
              onChange={() => setField('partShipOk', false)}
            />
            No
          </label>
        </fieldset>
      </div>

      <p className="ship-window-note">Please allow 7–12 days for transit.</p>
    </section>
  )
}
