// Customer-filled orders only. A rep never sees this section: the policies and
// the signature are both the BUYER's to give, and a rep-filled order hasn't
// reached them yet — they get the same section on the signing page instead.
// App.jsx decides, so there is no gate in here.
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
          Buyer's signature (type your full name)<span className="req">*</span>
          <input
            type="text"
            className="signature-input"
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
        <span>I have read and accept the Order Policies.<span className="req">*</span></span>
      </label>

      <label className="check">
        <input
          type="checkbox"
          checked={terms.infoConfirmed}
          onChange={(e) => setTerms('infoConfirmed', e.target.checked)}
        />
        <span>I confirm all the order information is correct.<span className="req">*</span></span>
      </label>

      {/* No "email me a copy" checkbox: every buyer gets the order copy at
          their Ship To address, and their rep is CC'd. */}
      <p className="order-copy-note">
        A copy of this order form will be emailed to you and to your sales
        representative. It is a copy for your records, not an order
        confirmation — you'll receive a Sales Order Confirmation separately.
      </p>

    </section>
  )
}
