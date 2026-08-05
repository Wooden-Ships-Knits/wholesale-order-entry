// Asked before any of the order form is rendered. The form's shape depends on
// the answer — Internal Use is rep-only, Terms/Signature is customer-only — and
// an unanswered question falls through to the customer branch everywhere, so
// without this a rep starts filling in the wrong layout and watches sections
// move once they answer. The radios stay in the order header afterwards, so
// this gates starting, not changing your mind.
export default function FilledByGate({ onChoose }) {
  return (
    <main className="order-form filled-by-gate">
      <div className="brand">
        <img src="/ws-logo-black.png" alt="Wooden Ships — Paola Buendia" className="brand-logo" />
      </div>
      {/* The greeting carries the warmth; the question stays the plain
          instruction underneath it. */}
      <p className="gate-question">Hi!, who is filling out this order form?</p>
      <div className="gate-choices">
        <button type="button" onClick={() => onChoose(true)}>
          Sales Representative
        </button>
        <button type="button" onClick={() => onChoose(false)}>
          Customer
        </button>
      </div>
    </main>
  )
}
