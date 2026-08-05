export default function Footer() {
  return (
    <footer className="form-footer">
      {/* Order matters: the middle one is the anchor, centred on the form, and
          the outer two are spaced equally from it. Kept in step with the PDF
          footers, backend/app/pdf/template*.html */}
      <span>www.woodenships-wholesale.com</span>
      <span>www.wooden-ships.com</span>
      <span>@woodenshipsknits</span>
    </footer>
  )
}
