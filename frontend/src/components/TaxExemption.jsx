export default function TaxExemption({ tax, setTax, certOnFile, setCertOnFile }) {
  return (
    <section className="section tax-exemption">
      <h2>Tax exemption certificate</h2>
      <label className="check">
        <input
          type="checkbox"
          checked={tax.repNotified}
          onChange={(e) => setTax('repNotified', e.target.checked)}
        />
        Rep has notified the account that a state-issued tax exemption certificate is required.
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={tax.sendingCert}
          onChange={(e) => setTax('sendingCert', e.target.checked)}
        />
        Account confirms it is sending the certificate — orders will not be processed without it.
      </label>
      <label className="check internal">
        <input type="checkbox" checked={certOnFile} onChange={(e) => setCertOnFile(e.target.checked)} />
        Certificate on file <span className="muted">(internal)</span>
      </label>
    </section>
  )
}
