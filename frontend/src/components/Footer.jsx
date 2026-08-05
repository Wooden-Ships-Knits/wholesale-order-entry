export default function Footer() {
  return (
    <footer className="form-footer">
      {/* Order matters: the middle one is the anchor, centred on the form, and
          the outer two are spaced equally from it. The longest string sits in
          the middle so the two flanking it are closer in length. Kept in step
          with the PDF footers, backend/app/pdf/template*.html */}
      <span>www.wooden-ships.com</span>
      <span>www.woodenships-wholesale.com</span>
      <span>@woodenshipsknits</span>
    </footer>
  )
}
