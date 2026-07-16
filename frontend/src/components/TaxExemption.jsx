export default function TaxExemption({ certFile, setCertFile }) {
  return (
    <section className="section tax-exemption">
      <h2>Tax exemption certificate</h2>
      <label>
        Upload certificate
        <input
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          onChange={(e) => setCertFile(e.target.files[0] || null)}
        />
      </label>
      {certFile && <span className="muted">{certFile.name}</span>}
    </section>
  )
}
