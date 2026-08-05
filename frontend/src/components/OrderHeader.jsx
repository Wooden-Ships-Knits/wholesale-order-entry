// Two header treatments for the "Filled by" answer, switched by ?v=back so
// both can be compared side by side (see App.jsx headerVariant):
//   'radios' (default) — the radio pair, changeable in place. Unchanged.
//   'back'             — radios removed; a Back link returns to the gate, and
//                        a line states which mode the form is in, since
//                        nothing else on the page says so.
export default function OrderHeader({
  seasons,
  season,
  onSeasonChange,
  form,
  setField,
  totalAmount,
  shipWindows = [],
  variant = 'radios',
  onBack,
}) {
  const isBack = variant === 'back'

  // Rendered in a different slot per variant — row 1 beside "Filled by" in the
  // default, row 2 after Ship Window in 'back'. Declared once so the two paths
  // cannot drift apart.
  const poField = (
    <label className="ha-po">
      PO # (optional)
      <input type="text" value={form.poNumber} onChange={(e) => setField('poNumber', e.target.value)} />
    </label>
  )

  return (
    <section className="section order-header">
      {/* Top-left of the section, on its own line above the centred logo.
          type="button" matters: this sits inside the order <form>, and a bare
          button would submit it. The arrow is decorative — the label carries
          the meaning for a screen reader. */}
      {isBack && (
        <button type="button" className="back-link" onClick={onBack}>
          <span className="back-arrow" aria-hidden="true">
            ←
          </span>
          Back
        </button>
      )}

      <div className="brand">
        <img src="/ws-logo-black.png" alt="Wooden Ships — Paola Buendia" className="brand-logo" />
      </div>

      <div className={isBack ? 'header-grid hg-back' : 'header-grid'}>
        {/* Row 1: Filled by (left) · PO # (middle) · Order total (right)
            'back' variant: mode statement (left) · Order total (right), with
            PO # moved down beside the other order fields. */}
        {isBack ? (
          <p className="ha-filled filled-as">
            Filling out as{' '}
            <strong>{form.representativeOk === true ? 'Sales Representative' : 'Customer'}</strong>
          </p>
        ) : (
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
        )}

        {/* Default variant: sits beside "Filled by" because either side can
            supply it — a rep keying a non-show order, or a customer with their
            own PO. */}
        {!isBack && poField}

        <div className="field ha-total">
          <span className="field-label">Order total</span>
          <span className="order-total">
            ${totalAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
        </div>

        {/* Row 2: Order date · Collection · Ship window (· PO # in 'back') */}
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

        {/* 'back' variant: PO # joins the order fields. Rendered here rather
            than placed by grid-area alone so the tab order follows what the
            eye sees. */}
        {isBack && poField}
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
