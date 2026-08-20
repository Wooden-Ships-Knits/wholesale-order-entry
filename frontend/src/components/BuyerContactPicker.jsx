// The account's contacts, offered inside the Bill To "Buyer name" field itself
// rather than as a control beside it. A <datalist> renders nothing of its own —
// it just hangs suggestions off the input named by `id`, so the form still has
// exactly one Buyer name field and that field is still free text.
//
// Why offer them at all: autofill names one person, but a store often has
// several and only a rep knows which one this order is for — Burlington Coat
// Factory keeps a sweater buyer and an accessory buyer, and Salesforce can flag
// only one of them as the buying contact.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
export default function BuyerContactPicker({ id, contacts = [] }) {
  // One contact is not a choice: autofill has already put them in the field, so
  // a list there would offer back the answer it just gave.
  if (contacts.length < 2) return null

  return (
    <datalist id={id}>
      {contacts.map((c) => (
        // value is the name alone — that is what lands in the field when it is
        // picked. The title rides in `label`, which browsers show beside the
        // name and never insert; a browser that ignores it just shows the name,
        // which is the part that matters. Ex-staff carry their "no longer"
        // title here, since a datalist has no way to grey an entry.
        <option key={c.name} value={c.name} label={c.title || undefined} />
      ))}
    </datalist>
  )
}
