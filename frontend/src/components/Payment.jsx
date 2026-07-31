// Card fields live only in React state and (in Phase 3+) the submit request
// body. They are never persisted client-side (no localStorage etc.).
/** "4111111111111111" -> "4111 1111 1111 1111".
 *
 * Both formatters rebuild from the digits alone rather than editing the string
 * in place. That keeps deleting sane: backspacing over a space or the slash
 * removes the digit before it instead of the separator reappearing and
 * trapping the caret. 19 digits covers every card network.
 */
function formatCardNumber(value) {
  const digits = value.replace(/\D/g, '').slice(0, 19)
  return digits.replace(/(\d{4})(?=\d)/g, '$1 ')
}

/** "0729" -> "07/29". The slash appears only once a third digit is typed, so
 *  "07" can still be backspaced down to "0" without it fighting the user. */
function formatExpDate(value) {
  const digits = value.replace(/\D/g, '').slice(0, 4)
  return digits.length >= 3 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits
}

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
            checked={payment.method === 'Credit Card'}
            onChange={() => setPayment('method', 'Credit Card')}
          />
          Credit Card
        </label>
        <label>
          <input
            type="radio"
            name="paymentMethod"
            checked={payment.method === 'PayPal'}
            onChange={() => setPayment('method', 'PayPal')}
          />
          PayPal
        </label>
      </fieldset>

      {payment.method === 'Credit Card' && (
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
                onChange={(e) => setPayment('cardNumber', formatCardNumber(e.target.value))}
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
                onChange={(e) => setPayment('expDate', formatExpDate(e.target.value))}
              />
            </label>
          </div>
        </>
      )}

      {payment.method === 'PayPal' && (
        <>
          <p className="muted small">
            A secure payment link will be emailed to you as the start ship date approaches.
          </p>
        </>
      )}
    </section>
  )
}
