export default function TermsSignature({ terms, setTerms }) {
  return (
    <section className="section terms">
      {/* <h2>Terms &amp; conditions</h2> */}
      <h2>ORDER POLICIES</h2>
      {/* TODO: replace with the exact wording from the Excel form
          (F26 - WS PDF Order Form.xlsx) once provided. Topics per PRD §5.8. */}
      <div className="terms-text">
        {/* <p>
          All Wooden Ships sweaters are <strong>made to order</strong>. Quantities may be adjusted to meet
          production minimums; you will be contacted before any adjustment is made. Claims for damages or
          shortages must be reported within <strong>10 days</strong> of receipt. Returns are not accepted without prior
          authorization and are subject to a restocking fee. All sale items are <strong>final sale</strong>.
          Orders ship via <strong>DHL</strong> unless otherwise arranged; freight is payable by the buyer.
          
          All Orders are always Net Due prior to shipment. We do not offer net terms. Please let us know within <strong>10 days</strong> 
          if you do not agree to these terms. If we don't hear from you, we'll understand this as an acceptance of 
          the terms and will proceed to purchase the yarn. Cancelled orders incur a 15% Restocking Fee.
        </p> */}

      <ul>
        <li>
          All Wooden Ships are <strong>made to order</strong>.
        </li>
        <li>
          Changes to your order may be requested within <strong>10 days of order confirmation</strong>.
        </li>
        <li>
          Claims for shipping damage or shortages must be reported within{' '}
          <strong>10 days of receiving your order</strong>.
        </li>
        <li>
          Cancelled orders are subject to a <strong>15% restocking fee</strong>.
        </li>
        <li>
          Custom and special orders are <strong>final sale</strong> and are not eligible for
          cancellation, return, or refund once production has begun.
        </li>
      </ul>
      <p>
        All Orders are always Net Due prior to shipment. We do not offer net terms. Please let us know within 10 days if you do not agree to these terms. If we don't hear from you, we'll understand this as an acceptance of the terms and will proceed to purchase the yarn. Cancelled orders incur a 15% Restocking Fee.
      </p>
      </div>
      
      <div className="signature-grid">
        <label>
          Buyer's signature (type your full name)
          <input
            type="text"
            value={terms.signatureName}
            onChange={(e) => setTerms('signatureName', e.target.value)}
            required
          />
        </label>
        {/* <label>
          Date
          <input
            type="date"
            value={terms.signatureDate}
            onChange={(e) => setTerms('signatureDate', e.target.value)}
          />
        </label> */}
      </div>
      
      <label className="check">
        <input
          type="checkbox"
          checked={terms.accepted}
          onChange={(e) => setTerms('accepted', e.target.checked)}
        />
        I have read and accept the Order Policies. <span className="req">*</span>
      </label>
    </section>
  )
}
