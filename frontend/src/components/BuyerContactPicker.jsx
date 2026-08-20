// The rep's shortcut for Bill To "Buyer name". Autofill names one person, but a
// store often has several and only a rep knows which one this order is for —
// Burlington Coat Factory keeps a sweater buyer and an accessory buyer, and
// Salesforce can flag only one of them as the buying contact.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
export default function BuyerContactPicker({ contacts = [], selected = '', onPick }) {
  // One contact is not a choice: autofill has already put them in the field, so
  // a dropdown there would offer the answer it just gave. Only a store with
  // several people has anything to ask about — 782 of them.
  if (contacts.length < 2) return null

  const current = selected.trim().toLowerCase()
  const match = contacts.find((c) => c.name.trim().toLowerCase() === current)

  // Ex-staff stay on the list — LILY'S BOUTIQUE's only two contacts are both
  // gone, and an empty picker there would tell the rep nothing — but they go
  // in their own group. A <select> can't grey an option, so the group label
  // carries what the greyed-out chip used to.
  const here = contacts.filter((c) => !c.former)
  const gone = contacts.filter((c) => c.former)

  const option = (c) => (
    <option key={c.name} value={c.name}>
      {c.title ? `${c.name} — ${c.title}` : c.name}
    </option>
  )

  return (
    <label className="buyer-contacts">
      Or pick a contact
      <select
        className="match-select"
        // Reflects the field rather than owning it: type a name by hand and
        // this falls back to the placeholder, because nobody on the list is
        // who the order is for any more.
        value={match ? match.name : ''}
        onChange={(e) => e.target.value && onPick(e.target.value)}
      >
        <option value="" disabled>
          {contacts.length} contacts on this account…
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
