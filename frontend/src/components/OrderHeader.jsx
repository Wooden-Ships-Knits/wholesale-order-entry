// "Filled by" is answered on the gate screen before this renders
// (components/FilledByGate.jsx), so the header states the answer rather than
// asking for it, and offers a way back to change it.
export default function OrderHeader({
  seasons,
  season,
  onSeasonChange,
  form,
  setField,
  totalAmount,
  shipWindows = [],
  onBack,
}) {
  return (
    <section className="section order-header">
      {/* Top-left of the section, on its own line above the centred logo.
          type="button" matters: this sits inside the order <form>, and a bare
          button would submit it. The arrow is decorative — the label carries
          the meaning for a screen reader. */}
      <button type="button" className="back-link" onClick={onBack}>
        <span className="back-arrow" aria-hidden="true">
          ←
        </span>
        Back
      </button>

      <div className="brand">
        <img src="/ws-logo-black.png" alt="Wooden Ships — Paola Buendia" className="brand-logo" />
      </div>

      <div className="header-grid">
        {/* Row 1: who is filling this in (left) · Order total (right) */}
        <p className="ha-filled filled-as">
          Filling out as{' '}
          <strong>{form.representativeOk === true ? 'Sales Representative' : 'Customer'}</strong>
        </p>

        <div className="field ha-total">
          <span className="field-label">Order total</span>
          <span className="order-total">
            ${totalAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        {/* Row 2: Order date · Collection · Ship window · PO # */}
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

        {/* Either side can supply a PO — a rep keying a non-show order, or a
            customer with their own. Rendered here rather than placed into the
            last column by grid-area alone, so tab order follows what the eye
            sees. */}
        <label className="ha-po">
          PO # (optional)
          <input type="text" value={form.poNumber} onChange={(e) => setField('poNumber', e.target.value)} />
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
