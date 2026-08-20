# Autofill Bill To "Buyer name" from the Salesforce buying contact

**Date:** 2026-08-20
**Status:** approved, ready for implementation

## Problem

`Bill To → Buyer name` is the only address field the account lookup does not
fill. `applyAccount()` (`frontend/src/App.jsx:172`) sets it to `''` on purpose:
until commit `ef1c8e2` ("feat:fix store buyer", 2026-07-22) it was filled with
`Account.Name`, which is the **store**, not a person. That commit gave the store
its own `form.accountName` field and left Buyer name blank rather than keep
filling it with the wrong thing.

Blank was correct at the time because `map_account()` returned no person name.
Salesforce does hold one — we were never asking for it.

## Source of truth

`Account.ContactBuying__c` is a **lookup to Contact** (relationship
`ContactBuying__r`, `calculated: false`) — verified against the org 2026-08-20.
`ContactBuyingEmail__c`, already the canonical buyer-lookup key
(`mapping.ACCOUNT_LOOKUP_EMAIL`), is a **formula over that same contact's
Email**. Confirmed on live records:

| Account | `ContactBuying__r.Name` | `ContactBuying__r.Email` | `ContactBuyingEmail__c` |
|---|---|---|---|
| BIRCH | Kathleen Belavitch | kbela@comcast.net | kbela@comcast.net |
| HOOKERS | Marilyn Davis | marilyn@flyfishglenwood.com | marilyn@flyfishglenwood.com |

So the person whose name we want is already the person whose email identifies
the account. `ContactBuying__r.Name` is that person's name.

### Why not join Contact on AccountId alone

The originally proposed `Contact.AccountId = Account.Id` join returns 7,651
contacts across 4,814 business accounts, and **1,254 of those accounts (26%)
have more than one contact** — up to 14. The join cannot say which one is the
buyer, and Contact carries no "primary" flag in this org (checked via describe).
`ContactBuying__r` is the org's own answer to that question. The join is kept
only as a fallback, and only where it is unambiguous.

## Coverage

5,059 wholesale business accounts (`IsPersonAccount = FALSE`):

| Source | Accounts |
|---|---|
| `ContactBuying__r.Name` | 4,731 (93.5%) |
| Fallback — sole related Contact | 12 |
| Fallback — sole Contact titled "Buyer" | 9 |
| **Filled** | **4,752 (93.9%)** |
| Left blank — several indistinguishable contacts | 67 |
| Left blank — no contact at all | 240 |

## Resolution rule

New `_buyer_name(rec)` in `app/salesforce/mapping.py`:

1. `ContactBuying__r.Name`, if non-blank → use it.
2. Otherwise, over related Contacts with a non-blank `Name`:
   - exactly one contact → use it;
   - several, but exactly one whose `Title` contains `"buyer"` (case-insensitive)
     and does **not** contain `"no longer"` → use it;
   - anything else → `None`.
3. `None` → the field stays empty and is typed by hand, exactly as today.

The `"no longer"` exclusion is not hypothetical: `ANTHROPOLOGIE EUROPE` and
`URBAN OUTFITTERS UK LTD` each carry contacts titled "no longer", and `QVC`'s
two contacts are *both* marked as having left.

### Why ambiguous accounts are left blank, not guessed

Buyer name is a required field on an order that gets signed. A wrong name is
worse than an empty one — the buyer must notice and correct it, and if they do
not, the order carries the wrong person. The ambiguous set has no usable signal:
"newest created" and "newest modified" disagree on 42 of the 76 multi-contact
accounts, and the sets are full of stale and non-buying staff.

## Rep contact picker

Autofill decides one name. A rep often needs a different one: `BURLINGTON COAT
FACTORY` has a *sweater buyer* and an *accessory buyer*, and `ContactBuying__c`
can only name one of them. So the account's contacts are also offered as
clickable chips under the Buyer name field.

**Shown to reps only** (`isRepFilled`), **whenever the account has at least one
contact**. Of 3,175 accounts reachable in the buyer lookup, 3,057 (96.3%) have
one or more; the other 118 behave exactly as today. A single-contact account
still shows its one chip — the rep sees who Salesforce thinks the buyer is.

The picker does not change `_buyer_name()`. Ambiguous accounts still prefill
blank; the chips just make the answer one click away instead of a retype.

Rep-ness here is a self-declared button, not authentication — the same soft gate
the conflict-warning modal already uses (CLAUDE.md: "stockist names hidden from
customers").

### Payload

`map_account()` returns, alongside `buyerName`:

```python
"contacts": [{"name": "Melanie Szczur", "title": "sweater buyer", "former": False}, ...]
```

Built from the `(SELECT Name, Title FROM Contacts ORDER BY Name)` subquery that `buyerName`
already needs — **no additional query** — under three rules:

1. **The buying contact comes first and is always included**, even when it is
   not a child of this account. This is not hypothetical: 25 accounts point
   `ContactBuying__c` at a contact belonging to a *different* account
   (`SAND PEOPLE - LAHAINA` → Laura Phillipson), and one at a contact with no
   account at all (`REAR VIEW MIRROR`). Rendering only the child records would
   show a prefilled name that is missing from the list beneath it. The list is
   a union, not the child records alone.
2. **De-duplicated by name**, since the buying contact is normally also a child.
3. **`former: true`** when the title contains "no longer" (284 contacts).
   Those sort last and render greyed — not hidden, because `LILY'S BOUTIQUE`'s
   only two contacts are both ex-staff and an empty picker there would tell the
   rep nothing.

Each chip shows name and title, because the title is what makes the choice
decidable. Emails are deliberately left out — see below.

4. **Contacts whose name is a mailbox are dropped entirely.** `Contact.Name` is
   free text and eight records hold things like `Postmaster@coat.com` and
   `Receiving@joanshepp.com`, six of them on reachable accounts. They are not
   people, they are useless as a Bill To buyer, and offering one as a chip
   would put a real address on a public endpoint one click from a signed order.
   Dropping them also *sharpens* the fallback instead of narrowing it: `JOAN
   SHEPP` now resolves to "Joan Shepp", because the receiving mailbox beside
   her no longer makes the choice look ambiguous.

### Known exposure

`GET /api/accounts` is public and unauthenticated, and the rep gate is a
self-declared button, so the contact list is readable by anyone who looks,
customer or not. The endpoint already returns the store's `Tax_ID_Number__c`,
phone and buying email, so this is not a new category of exposure, but it does
widen it from one person to all staff. Accepted as consistent with the existing
surface; gating it properly would mean requiring rep sign-in on the order form,
which would change the normal flow.

Contact **emails** are kept out of the payload to avoid widening it further —
and, because `Contact.Name` is itself free text that sometimes holds an
address, that means dropping mailbox-shaped names too (rule 4 above). Selecting
no email field is not sufficient on this data; the final review caught that the
original wording assumed it was.

## Implementation

### Backend

`app/salesforce/mapping.py`
- `CONTACT_BUYING_NAME = "ContactBuying__r.Name"` and
  `CONTACT_BUYING_TITLE = "ContactBuying__r.Title"`, added to `ACCOUNT_FIELDS`.
  (`ContactBuying__c` itself is never selected or filtered on, so it gets no
  constant — the traversals are all we need.)
- New `_account_contacts(rec)` building the picker list per the rules above.
- New `ACCOUNT_CONTACTS_SUBQUERY = "(SELECT Name, Title FROM Contacts ORDER BY Name)"`, kept
  separate so `ACCOUNT_FIELDS` stays a tuple of scalar fields. Salesforce field
  names remain confined to this module (CLAUDE.md rule 4).
- New `_buyer_name(rec)` implementing the rule above.
- `map_account()` gains `"buyerName": _buyer_name(rec)` and
  `"contacts": _account_contacts(rec)`.

`app/salesforce/client.py`
- `find_accounts()` appends the child subquery to its SELECT.

The result is still **one SOQL call** — the child subquery rides along with the
existing query, verified against the org. No extra round-trip, no N+1.

### Frontend

`frontend/src/App.jsx`, in `applyAccount()`:

```js
buyerName: m.buyerName || '',   // was: buyerName: ''
```

The field stays editable, required, and title-cased on blur. Selecting a
different account overwrites it, because `applyAccount()` already replaces the
whole `billTo` object.

New `frontend/src/components/BuyerContactPicker.jsx` — one job: render the chips
and report a click. `Addresses.jsx` renders it under the Buyer name field and is
otherwise untouched.

The rep gate lives in `App.jsx`, where `isRepFilled` already does:

```jsx
buyerContacts={isRepFilled ? accountContacts : []}
```

so `Addresses` stays unaware of who is filling the form and renders what it is
handed. `applyAccount()` stores `accountContacts`; a lookup matching nothing
clears it. Clicking a chip sets `billTo.buyerName` — the field remains free
text, so a rep can still name someone Salesforce has never heard of.

No frontend test framework exists in this repo, so the picker is verified by
`npm run build` plus a runtime pass with the `verify` skill. Introducing vitest
is out of scope here.

### Blast radius

`ACCOUNT_FIELDS` has exactly one consumer (`client.py:470`), and `/api/accounts`
returns plain dicts with no Pydantic response model, so the change is additive.
The admin account picker calls the same `find_accounts()` and simply gains the
field.

## Testing

New `backend/tests/test_account_mapping.py` — `map_account` has no coverage
today. Cases:

1. `ContactBuying__r.Name` present → returned.
2. `ContactBuying__r` null, one related contact → that contact.
3. `ContactBuying__r` null, several contacts, one titled "Buyer" → that one.
4. `ContactBuying__r` null, several contacts, no distinguishing title → `None`.
5. A "buyer"-titled contact also marked "no longer" → excluded.
6. No contacts at all → `None`.
7. Blank/whitespace contact names ignored.

## Data quality follow-up (not code)

`docs/releases/buyer-name-gaps.csv` lists all 328 accounts with no
`ContactBuying__c`, categorised, with their candidate contacts. Setting
`ContactBuying__c` on the 49 ambiguous accounts that are actually reachable in
the buyer lookup would close most of the remaining gap; the rest are hidden by
the `EXCLUDED_RANKS_FIND_ACCOUNT` filter and never reach the form.
