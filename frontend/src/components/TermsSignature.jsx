export default function TermsSignature({ terms, setTerms }) {
  return (
    <section className="section terms">
      <h2>Terms &amp; conditions</h2>
      {/* TODO: replace with the exact wording from the Excel form
          (F26 - WS PDF Order Form.xlsx) once provided. Topics per PRD §5.8. */}
      <div className="terms-text">
        <p>
          All Wooden Ships sweaters are <strong>made to order</strong>. Quantities may be adjusted to meet
          production minimums; you will be contacted before any adjustment is made. Claims for damages or
          shortages must be reported within 10 days of receipt. Returns are not accepted without prior
          authorization and are subject to a restocking fee. All sale items are <strong>final sale</strong>.
          Orders ship via <strong>DHL</strong> unless otherwise arranged; freight is payable by the buyer.
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
        <label>
          Date
          <input
            type="date"
            value={terms.signatureDate}
            onChange={(e) => setTerms('signatureDate', e.target.value)}
          />
        </label>
      </div>
      <label className="check">
        <input
          type="checkbox"
          checked={terms.accepted}
          onChange={(e) => setTerms('accepted', e.target.checked)}
        />
        I have read and accept the terms &amp; conditions. <span className="req">*</span>
      </label>
    </section>
  )
}
