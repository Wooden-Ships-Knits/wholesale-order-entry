// Bill To "Buyer name", rendered as a dropdown instead of a text box when the
// account has more than one contact — the same `label > select` markup as
// Internal Use's "Order written by", so it needs no styling of its own.
//
// It REPLACES the text input rather than sitting beside it: the form shows one
// control for Buyer name, never two. Addresses.jsx chooses which.
//
// The tradeoff, decided deliberately: on these accounts a rep can only name a
// contact Salesforce already knows. Accounts with one contact or none — new
// accounts included — keep the free-text field, which is where a genuinely new
// buyer gets entered.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
export default function BuyerContactPicker({ contacts = [], value = '', onPick }) {
  // Ex-staff stay selectable — LILY'S BOUTIQUE's only two contacts are both
  // gone, and hiding them would leave nobody to pick — but in their own group.
  // A <select> can't grey an option, so the group label does that work.
  const here = contacts.filter((c) => !c.former)
  const gone = contacts.filter((c) => c.former)

  const option = (c) => (
    <option key={c.name} value={c.name}>
      {c.title ? `${c.name} — ${c.title}` : c.name}
    </option>
  )

  return (
    <label>
      Buyer name<span className="req">*</span>
      <select value={value} onChange={(e) => onPick(e.target.value)} required>
        {/* Empty until the rep chooses, so an ambiguous account cannot submit
            whoever happens to sort first. `required` blocks that. */}
        <option value="" disabled>
          Select the buyer…
        </option>
        {gone.length > 0 ? (
          <optgroup label="Current">{here.map(option)}</optgroup>
        ) : (
          here.map(option)
        )}
        {gone.length > 0 && (
          <optgroup label="No longer here">{gone.map(option)}</optgroup>
        )}
      </select>
    </label>
  )
}
