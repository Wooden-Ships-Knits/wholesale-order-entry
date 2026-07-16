export default function Notes({ notes, setNotes }) {
  return (
    <section className="section notes">
      <h2>Notes</h2>
      <textarea
        rows="4"
        placeholder="Enter any additional notes here…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
    </section>
  )
}