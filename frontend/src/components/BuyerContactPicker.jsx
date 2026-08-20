// The rep's shortcut for Bill To "Buyer name". Autofill names one person, but a
// store often has several and only a rep knows which one this order is for —
// Burlington Coat Factory keeps a sweater buyer and an accessory buyer, and
// Salesforce can flag only one of them as the buying contact.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
// Contacts arrive best-first with ex-staff last; rendering order is theirs.
export default function BuyerContactPicker({ contacts = [], selected = '', onPick }) {
  if (!contacts.length) return null

  const current = selected.trim().toLowerCase()

  return (
    <div className="buyer-contacts">
      <span className="buyer-contacts-label" id="buyer-contacts-label">
        Contacts on this account
      </span>
      {/* Sighted users get the grouping from proximity; someone tabbing in
          from the Buyer name field would otherwise hear only a bare name. */}
      <ul className="buyer-contacts-list" aria-labelledby="buyer-contacts-label">
        {contacts.map((c) => {
          // Trimmed both sides: the backend strips names, but this must not
          // quietly depend on that to keep the right chip lit.
          const isSelected = c.name.trim().toLowerCase() === current
          return (
            <li key={c.name}>
              <button
                type="button"
                className={
                  'contact-chip' +
                  (isSelected ? ' is-selected' : '') +
                  (c.former ? ' is-former' : '')
                }
                // A toggle-like control, so state has to reach a screen reader.
                aria-pressed={isSelected}
                onClick={() => onPick(c.name)}
              >
                <span className="contact-name">{c.name}</span>
                {c.title && <span className="contact-title">{c.title}</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
