// Card fields live only in React state and (in Phase 3+) the submit request
// body. They are never persisted client-side (no localStorage etc.).
export default function Payment({ payment, setPayment }) {
  return (
    <section className="section payment">
      <h2>Payment</h2>

      <fieldset className="inline-radios">
        <legend>Payment method</legend>
        <label>
          <input
            type="radio"
            name="paymentMethod"
            checked={payment.method === 'direct'}
            onChange={() => setPayment('method', 'direct')}
          />
          Direct
        </label>
        <label>
          <input
            type="radio"
            name="paymentMethod"
            checked={payment.method === 'store'}
            onChange={() => setPayment('method', 'store')}
          />
          Store your card
        </label>
      </fieldset>

      {payment.method === 'direct' && (
        <>
          <fieldset className="inline-radios">
            <legend>Payment type</legend>
            <label>
              <input
                type="radio"
                name="directPaymentType"
                checked={payment.directType === 'card'}
                onChange={() => setPayment('directType', 'card')}
              />
              Credit Card
            </label>
            <label>
              <input
                type="radio"
                name="directPaymentType"
                checked={payment.directType === 'paypal'}
                onChange={() => setPayment('directType', 'paypal')}
              />
              PayPal
            </label>
          </fieldset>
          <p className="muted small">
            A secure payment link will be emailed to you as the start ship date approaches.
          </p>
        </>
      )}

      {payment.method === 'store' && (
        <>
          <fieldset className="inline-radios">
            <legend>Charge approval</legend>
            <label>
              <input
                type="radio"
                name="approvalBeforeCharge"
                checked={payment.approvalBeforeCharge === true}
                onChange={() => setPayment('approvalBeforeCharge', true)}
              />
              Get approval before charging
            </label>
            <label>
              <input
                type="radio"
                name="approvalBeforeCharge"
                checked={payment.approvalBeforeCharge === false}
                onChange={() => setPayment('approvalBeforeCharge', false)}
              />
              Charge without approval
            </label>
          </fieldset>

          <div className="payment-grid">
            <label className="span2">
              Credit card number
              <input
                type="text"
                inputMode="numeric"
                autoComplete="cc-number"
                maxLength="23"
                value={payment.cardNumber}
                onChange={(e) => setPayment('cardNumber', e.target.value.replace(/[^\d ]/g, ''))}
              />
            </label>
            <label className="span2">
              Name as it appears on card
              <input
                type="text"
                autoComplete="cc-name"
                value={payment.cardName}
                onChange={(e) => setPayment('cardName', e.target.value)}
              />
            </label>
            <label>
              Exp date (MM/YY)
              <input
                type="text"
                inputMode="numeric"
                autoComplete="cc-exp"
                placeholder="MM/YY"
                maxLength="5"
                value={payment.expDate}
                onChange={(e) => setPayment('expDate', e.target.value)}
              />
            </label>
          </div>
          <p className="muted small">
            Card details are used once by our admin team to process this order and are not stored.
          </p>
        </>
      )}
    </section>
  )
}
