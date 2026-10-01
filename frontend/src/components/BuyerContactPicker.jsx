// Bill To "Buyer name", rendered as a dropdown instead of a text box when the
// account has more than one contact — the same `label > select` markup as
// Internal Use's "Order written by", so it needs no styling of its own.
//
// It REPLACES the text input rather than sitting beside it: the form shows one
// control for Buyer name, never two. Addresses.jsx chooses which.
//
// A buyer Salesforce doesn't know yet is entered through "+ Add new buyer…",
// which swaps the dropdown for a text box (still one control, never two) with
// a link back to the list. Accounts with one contact or none — new accounts
// included — keep the plain free-text field.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
import { useState } from 'react'

// Sentinel <option> value for "type a new name"; can't collide with a contact.
const ADD_NEW = '__add_new_buyer__'

export default function BuyerContactPicker({ contacts = [], value = '', onPick, tidy = (v) => v }) {
  // Start in typing mode when the form already holds a name that isn't one of
  // the contacts (e.g. typed earlier, then the contact list loaded).
  const [adding, setAdding] = useState(
    () => Boolean(value) && !contacts.some((c) => c.name === value),
  )

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

  if (adding) {
    return (
      <label>
        Buyer name<span className="req">*</span>
        <input
          type="text"
          value={value}
          onChange={(e) => onPick(e.target.value)}
          onBlur={(e) => {
            const tidied = tidy(e.target.value)
            if (tidied !== e.target.value) onPick(tidied)
          }}
          autoComplete="name"
          placeholder="New buyer's name"
          required
          autoFocus
        />
        <button
          type="button"
          className="link-btn inline buyer-back"
          onClick={() => {
            setAdding(false)
            onPick('')
          }}
        >
          Choose from existing contacts
        </button>
      </label>
    )
  }

  const handleSelect = (e) => {
    if (e.target.value === ADD_NEW) {
      setAdding(true)
      onPick('')
      return
    }
    onPick(e.target.value)
  }

  return (
    <label>
      Buyer name<span className="req">*</span>
      <select value={value} onChange={handleSelect} required>
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
        <option value={ADD_NEW}>+ Add new buyer…</option>
      </select>
    </label>
  )
}
