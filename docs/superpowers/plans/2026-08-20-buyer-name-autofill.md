# Buyer Name Autofill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the Bill To "Buyer name" field automatically from the Salesforce buying contact, and let a rep pick a different contact from the account when the autofilled one isn't who this order is for.

**Architecture:** `Account.ContactBuying__c` is a lookup to Contact and is the org's own designation of the store's buyer — the same person whose email (`ContactBuyingEmail__c`, a formula over that contact) already identifies the account. The existing single SOQL in `find_accounts()` grows `ContactBuying__r.Name`, `ContactBuying__r.Title` and a `(SELECT Name, Title FROM Contacts ORDER BY Name)` child subquery, so nothing extra is queried. Two pure functions in the mapping module turn a record into (a) the one prefilled name and (b) the rep's list of choices. The frontend prefills the field and, for reps only, renders the list as clickable chips beneath it.

**Tech Stack:** Python 3.11, FastAPI, `simple-salesforce`, pytest, React + Vite, plain CSS.

**Spec:** `docs/superpowers/specs/2026-08-20-buyer-name-autofill-design.md`

---

## Background the engineer needs

**Read first:** `CLAUDE.md` rule 4 — Salesforce object/field names live only in
`backend/app/salesforce/mapping.py`, so a rename is a one-file change. Do not put
a Salesforce field name in `client.py`, a router, or the frontend.

**How the pieces connect today:**

1. The buyer types a store name or email into `frontend/src/components/BuyerLookup.jsx`.
2. That hits `GET /api/accounts` → `backend/app/routers/accounts.py:lookup_accounts`.
3. Which calls `client.find_accounts()` (`backend/app/salesforce/client.py:450-495`) — one SOQL.
4. Each record goes through `mapping.map_account()` (`backend/app/salesforce/mapping.py:281-306`) into the JSON the browser gets.
5. The browser hands that object to `applyAccount()` (`frontend/src/App.jsx:171-200`), which fills the form.

Step 4 is where the new fields are produced; step 5 is where they land in the form.

**Running the backend tests.** From the `backend/` directory:

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest -q
```

**Baseline before you start: `17 failed, 162 passed, 1 skipped`.** Those 17
failures are pre-existing on this branch and unrelated to this work
(`test_admin_row.py` ×6, `test_conflict_resolution.py` ×2, `test_order_email.py`
×4, `test_order_schema.py` ×4, `test_send_email.py` ×1 — mostly stale test
fixtures missing newer model attributes such as `ship_window`). **Do not fix
them in this plan.** Your job is to keep that count at 17 and add passing tests.

**There is no frontend test framework** in this repo (`frontend/package.json`
has only `dev`, `build`, `preview`). Frontend tasks verify with `npm run build`
plus a runtime pass using the project's `verify` skill
(`.claude/skills/verify/SKILL.md`). Do not add vitest — out of scope.

**SOQL note.** A "child subquery" is SOQL's way of pulling a parent's child
records inline: `SELECT Id, (SELECT Name FROM Contacts) FROM Account`. The
result puts them under a `Contacts` key as `{"records": [...]}` — or `None` if
the account has no contacts. `ContactBuying__r` is a parent traversal and comes
back as a nested dict, or `None` when the lookup is empty. Both shapes are
verified against the live org.

**One counterintuitive fact.** `ContactBuying__c` is a plain lookup, so the
buying contact is *not guaranteed* to be one of the account's own contacts.
25 accounts point it at a contact filed under a different account, and
`REAR VIEW MIRROR` points at one with no account at all. Task 3 depends on this.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/app/salesforce/mapping.py` | Field names + record→payload mapping | 3 constants, `_buyer_name()`, `_account_contacts()`, 2 `map_account()` keys |
| `backend/app/salesforce/client.py` | Builds and runs the SOQL | Append the child subquery to `find_accounts()`'s SELECT |
| `backend/tests/test_account_mapping.py` | Unit tests for the two mapping helpers | **Create** — `map_account` has no coverage today |
| `backend/tests/test_account_query.py` | Guards what the lookup SOQL selects | **Create** |
| `frontend/src/components/BuyerContactPicker.jsx` | Renders contact chips, reports a click | **Create** |
| `frontend/src/components/Addresses.jsx` | Bill To / Ship To fields | Render the picker under Buyer name |
| `frontend/src/App.jsx` | Form state; applies a looked-up account; owns the rep gate | Prefill the field, hold the contact list |
| `frontend/src/index.css` | All styling | Chip styles |
| `docs/architecture.md` | Salesforce field reference | Reclassify `ContactBuying__c` as used |

`ACCOUNT_FIELDS` has exactly one consumer (`client.py:470`) and `/api/accounts`
returns plain dicts with no Pydantic response model, so every backend change is
additive.

---

## Task 1: `_buyer_name()` resolves the buying contact

**Files:**
- Modify: `backend/app/salesforce/mapping.py` (constants near line 22; new function above `map_account` at line 281)
- Test: `backend/tests/test_account_mapping.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_account_mapping.py`:

```python
"""Buyer-name resolution from the Salesforce buying contact.

Coverage is on the rule itself: which contact becomes Bill To "Buyer name",
and — just as important — when we refuse to guess and leave it blank.
"""
from app.salesforce.mapping import _buyer_name


def _account(buying=None, buying_title=None, contacts=None):
    """Minimal Account record in the shape SOQL actually returns.

    ContactBuying__r is a parent traversal (nested dict or None); Contacts is
    a child subquery ({"records": [...]} or None when there are none).
    """
    return {
        "Id": "0012v00000AbCdEAAV",
        "Name": "A PIED",
        "ContactBuying__r": (
            {"Name": buying, "Title": buying_title} if buying is not None else None
        ),
        "Contacts": {"records": contacts} if contacts is not None else None,
    }


def _contact(name, title=None):
    return {"Name": name, "Title": title}


def test_uses_the_designated_buying_contact():
    assert _buyer_name(_account(buying="Kathleen Belavitch")) == "Kathleen Belavitch"


def test_buying_contact_wins_over_related_contacts():
    rec = _account(buying="Kathleen Belavitch", contacts=[_contact("Someone Else")])
    assert _buyer_name(rec) == "Kathleen Belavitch"


def test_falls_back_to_a_sole_related_contact():
    assert _buyer_name(_account(contacts=[_contact("Emily Egan")])) == "Emily Egan"


def test_falls_back_to_the_only_contact_titled_buyer():
    # FLEA (BROOKLYN) in the real org: three contacts, one titled "Buyer".
    rec = _account(contacts=[
        _contact("Pierre Pujos"),
        _contact("Jennifer Szymchack"),
        _contact("Ines Pujos", "Buyer"),
    ])
    assert _buyer_name(rec) == "Ines Pujos"


def test_buyer_title_match_ignores_case_and_surrounding_text():
    rec = _account(contacts=[
        _contact("Lisa Merritt", "BUYER apparel/hats"),
        _contact("Rob Skinner", "AP manager"),
    ])
    assert _buyer_name(rec) == "Lisa Merritt"


def test_ignores_a_buyer_who_no_longer_works_there():
    # A title can say "buyer" and "gone" at once. QVC's two contacts are both
    # ex-staff, so there is nobody left to name.
    rec = _account(contacts=[
        _contact("Amy Corey", "buyer - no longer there"),
        _contact("Mary Kate Mehl", "assistant"),
    ])
    assert _buyer_name(rec) is None


def test_a_current_buyer_still_wins_when_a_former_one_is_present():
    # Both titled buyer; only one of them still works there.
    rec = _account(contacts=[
        _contact("Sarah Burton", "Buyer - no longer"),
        _contact("Stefania Squitieri", "Buyer"),
    ])
    assert _buyer_name(rec) == "Stefania Squitieri"


def test_returns_none_when_two_contacts_are_both_titled_buyer():
    # THE BEAD EXPERIENCE: two contacts, both "_BUYER". No way to choose.
    rec = _account(contacts=[
        _contact("Idy", "_BUYER"),
        _contact("Julie Harris", "_BUYER"),
    ])
    assert _buyer_name(rec) is None


def test_returns_none_when_several_contacts_have_no_distinguishing_title():
    rec = _account(contacts=[_contact("Katie"), _contact("Laura")])
    assert _buyer_name(rec) is None


def test_returns_none_when_there_are_no_contacts_at_all():
    assert _buyer_name(_account()) is None


def test_ignores_contacts_with_a_blank_name():
    rec = _account(contacts=[_contact("   "), _contact("Heidi Jorgensen")])
    assert _buyer_name(rec) == "Heidi Jorgensen"


def test_treats_a_blank_buying_contact_name_as_absent():
    rec = _account(buying="  ", contacts=[_contact("Emily Egan")])
    assert _buyer_name(rec) == "Emily Egan"


def test_strips_surrounding_whitespace():
    assert _buyer_name(_account(buying="  Marilyn Davis ")) == "Marilyn Davis"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q
```

Expected: collection error — `ImportError: cannot import name '_buyer_name' from 'app.salesforce.mapping'`.

- [ ] **Step 3: Add the field constants**

In `backend/app/salesforce/mapping.py`, directly below the
`ACCOUNT_LOOKUP_EMAIL` block (around line 22):

```python
# The store's designated buyer: a real lookup to Contact (verified against the
# org 2026-08-20). ACCOUNT_LOOKUP_EMAIL above is a formula over this same
# contact's Email, so the buying contact IS the person the account lookup
# already identifies — we were simply never asking for their name.
#
# It is a lookup, not a master-detail, so the contact it points at is NOT
# guaranteed to belong to this account: 25 accounts point at a contact filed
# under a different one. _account_contacts() below depends on that.
CONTACT_BUYING_NAME = "ContactBuying__r.Name"
CONTACT_BUYING_TITLE = "ContactBuying__r.Title"

# Related contacts, as a child subquery, so a rep can pick a different person
# and so accounts with no ContactBuying__c still have something to offer. Kept
# out of ACCOUNT_FIELDS so that stays a tuple of scalar field names; client.py
# appends this to the SELECT.
ACCOUNT_CONTACTS_SUBQUERY = "(SELECT Name, Title FROM Contacts ORDER BY Name)"
```

- [ ] **Step 4: Add both traversals to `ACCOUNT_FIELDS`**

In the `ACCOUNT_FIELDS` tuple (line 155-177), add them after `ACCOUNT_LOOKUP_EMAIL`:

```python
    ACCOUNT_LOOKUP_EMAIL,
    CONTACT_BUYING_NAME,
    CONTACT_BUYING_TITLE,
```

- [ ] **Step 5: Implement `_buyer_name()`**

Add above `map_account()` in `backend/app/salesforce/mapping.py`:

```python
def _buyer_name(rec: dict[str, Any]) -> str | None:
    """The person for Bill To "Buyer name", or None to leave the field blank.

    The account's designated buying contact answers this for 93.5% of wholesale
    accounts. For the rest we fall back to a related Contact, but only when the
    choice is unambiguous: Buyer name is required on an order that gets signed,
    so a wrong name is worse than an empty one. 26% of accounts carry several
    contacts, Contact has no "primary" flag in this org, and the leftovers are
    full of ex-staff — there is nothing to guess from. Measured 2026-08-20:
    4,731 accounts resolve here, +21 by fallback, 307 stay blank.

    A rep who disagrees with the result picks from _account_contacts() instead.
    """
    buying = rec.get("ContactBuying__r") or {}
    name = (buying.get("Name") or "").strip()
    if name:
        return name

    contacts = (rec.get("Contacts") or {}).get("records") or []
    named = [c for c in contacts if (c.get("Name") or "").strip()]
    if len(named) == 1:
        return named[0]["Name"].strip()

    # Several contacts: a job title is the only signal, and it has to be a
    # CURRENT buyer. Titles like "no longer" / "no longer there" mark people
    # who left — naming them would be worse than naming nobody.
    buyers = [
        c
        for c in named
        if "buyer" in (c.get("Title") or "").lower()
        and "no longer" not in (c.get("Title") or "").lower()
    ]
    if len(buyers) == 1:
        return buyers[0]["Name"].strip()

    return None
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q
```

Expected: `13 passed`.

- [ ] **Step 7: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add backend/app/salesforce/mapping.py backend/tests/test_account_mapping.py
git commit -m "feat: resolve the buyer name from the Salesforce buying contact"
```

---

## Task 2: `map_account()` emits `buyerName`

**Files:**
- Modify: `backend/app/salesforce/mapping.py:281-306` (`map_account`)
- Test: `backend/tests/test_account_mapping.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_account_mapping.py`:

```python
from app.salesforce.mapping import map_account


def _sf_account(**over):
    """A full Account record as find_accounts() returns it."""
    base = {
        "Id": "0012v00000AbCdEAAV",
        "Name": "A PIED",
        "BillingStreet": "1 Main St",
        "BillingCity": "Nashville",
        "BillingState": "TN",
        "BillingPostalCode": "37201",
        "ShippingStreet": "1 Main St",
        "ShippingCity": "Nashville",
        "ShippingState": "TN",
        "ShippingPostalCode": "37201",
        "Phone": "(615) 555-0100",
        "Fax": None,
        "ContactBuyingEmail__c": "buyer@apied.com",
        "ContactBuying__r": {"Name": "Kathleen Belavitch", "Title": "Owner"},
        "Contacts": None,
        "Tax_ID_Number__c": None,
        "Tax_ID_Verified__c": False,
        "Tax_ID_Expires__c": None,
        "Salesperson__c": None,
        "SalesTerritory__c": None,
        "Special_Instructions__c": None,
        "Rank__c": None,
    }
    base.update(over)
    return base


def test_map_account_exposes_the_buyer_name():
    assert map_account(_sf_account())["buyerName"] == "Kathleen Belavitch"


def test_map_account_buyer_name_is_none_when_unresolvable():
    rec = _sf_account(ContactBuying__r=None, Contacts=None)
    assert map_account(rec)["buyerName"] is None


def test_map_account_still_reports_the_store_name_separately():
    """Buyer name is a person; name is the store. Conflating them was the bug
    that commit ef1c8e2 fixed — this pins them apart."""
    mapped = map_account(_sf_account())
    assert mapped["name"] == "A PIED"
    assert mapped["buyerName"] == "Kathleen Belavitch"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q -k map_account
```

Expected: FAIL with `KeyError: 'buyerName'`.

- [ ] **Step 3: Add the key to `map_account()`**

In `map_account()`, add `buyerName` directly after `"name"` so the store/person
pair reads together:

```python
    return {
        "accountId": rec["Id"],
        "name": rec.get("Name"),
        # The person, as opposed to `name` (the store). Fills Bill To "Buyer
        # name"; None when Salesforce cannot say who unambiguously, and the
        # form then leaves the field for the buyer to type.
        "buyerName": _buyer_name(rec),
        "billTo": {
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q
```

Expected: `16 passed`.

- [ ] **Step 5: Confirm nothing else regressed**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest -q 2>&1 | tail -3
```

Expected: `17 failed, 178 passed, 1 skipped` — the same 17 pre-existing
failures, 16 more passing than the 162 baseline.

- [ ] **Step 6: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add backend/app/salesforce/mapping.py backend/tests/test_account_mapping.py
git commit -m "feat: return buyerName from the account lookup payload"
```

---

## Task 3: `_account_contacts()` builds the rep's pick list

**Files:**
- Modify: `backend/app/salesforce/mapping.py` (new function beside `_buyer_name`; one more `map_account` key)
- Test: `backend/tests/test_account_mapping.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_account_mapping.py`:

```python
from app.salesforce.mapping import _account_contacts


def test_contacts_lead_with_the_buying_contact():
    rec = _account(
        buying="Kathleen Belavitch",
        buying_title="Owner",
        contacts=[_contact("Someone Else"), _contact("Kathleen Belavitch", "Owner")],
    )
    picked = _account_contacts(rec)
    assert picked[0] == {"name": "Kathleen Belavitch", "title": "Owner", "former": False}


def test_contacts_include_a_buying_contact_filed_under_another_account():
    """25 accounts point ContactBuying__c at a contact that is not their own
    child (SAND PEOPLE - LAHAINA -> Laura Phillipson). The prefilled name must
    still appear in the list, or the field names someone the picker doesn't."""
    rec = _account(buying="Laura Phillipson", contacts=[_contact("Front Desk")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Laura Phillipson", "Front Desk"]


def test_contacts_do_not_repeat_the_buying_contact():
    rec = _account(buying="Emily Egan", contacts=[_contact("Emily Egan")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Emily Egan"]


def test_contact_dedupe_ignores_case():
    rec = _account(buying="Emily Egan", contacts=[_contact("EMILY EGAN")])
    assert len(_account_contacts(rec)) == 1


def test_contacts_flag_former_staff():
    rec = _account(contacts=[_contact("Emma Hopkin", "no longer")])
    assert _account_contacts(rec) == [
        {"name": "Emma Hopkin", "title": "no longer", "former": True}
    ]


def test_contacts_sort_former_staff_last():
    rec = _account(contacts=[
        _contact("Emma Hopkin", "no longer"),
        _contact("Charlotte Glover"),
        _contact("Helen Webster", "no longer"),
        _contact("Sophie Jewell"),
    ])
    assert [c["name"] for c in _account_contacts(rec)] == [
        "Charlotte Glover", "Sophie Jewell", "Emma Hopkin", "Helen Webster",
    ]


def test_a_former_buying_contact_still_leads():
    """Ordering must agree with the prefilled value: _buyer_name() returns the
    buying contact regardless of title, so it cannot sort to the bottom."""
    rec = _account(
        buying="Yolanda", buying_title="no longer", contacts=[_contact("Ann")]
    )
    picked = _account_contacts(rec)
    assert picked[0]["name"] == "Yolanda"
    assert picked[0]["former"] is True


def test_contacts_have_no_title_key_value_when_untitled():
    rec = _account(contacts=[_contact("Katie")])
    assert _account_contacts(rec) == [{"name": "Katie", "title": None, "former": False}]


def test_contacts_skip_blank_names():
    rec = _account(contacts=[_contact("   "), _contact("Heidi Jorgensen")])
    assert [c["name"] for c in _account_contacts(rec)] == ["Heidi Jorgensen"]


def test_contacts_are_empty_when_the_account_has_none():
    assert _account_contacts(_account()) == []


def test_map_account_exposes_the_contact_list():
    rec = _sf_account(Contacts={"records": [{"Name": "Ann", "Title": None}]})
    assert map_account(rec)["contacts"] == [
        {"name": "Kathleen Belavitch", "title": "Owner", "former": False},
        {"name": "Ann", "title": None, "former": False},
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q
```

Expected: collection error — `ImportError: cannot import name '_account_contacts'`.

- [ ] **Step 3: Implement `_account_contacts()`**

Add directly below `_buyer_name()` in `backend/app/salesforce/mapping.py`:

```python
def _account_contacts(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Everyone a rep may pick as the buyer, best candidate first.

    Autofill names one person; a store often has several, and only a rep knows
    which one an order is for — BURLINGTON COAT FACTORY keeps a sweater buyer
    and an accessory buyer, and ContactBuying__c can only name one of them.

    The buying contact leads and is ALWAYS included, even when it is not a
    child of this account: ContactBuying__c is a plain lookup, and 25 accounts
    point it at a contact filed under a different one (plus REAR VIEW MIRROR,
    whose buying contact has no account at all). Listing only the child records
    would show a prefilled name missing from the list beneath it.

    Former staff stay in the list, marked and last — LILY'S BOUTIQUE's only two
    contacts are both titled "no longer", and an empty picker there would tell
    the rep nothing. The buying contact keeps its lead even when former, so the
    ordering cannot contradict the prefilled value.
    """
    def entry(c: dict[str, Any]) -> dict[str, Any]:
        title = (c.get("Title") or "").strip()
        return {
            "name": (c.get("Name") or "").strip(),
            "title": title or None,
            "former": "no longer" in title.lower(),
        }

    buying = rec.get("ContactBuying__r") or {}
    head = [entry(buying)] if (buying.get("Name") or "").strip() else []

    seen = {e["name"].casefold() for e in head}
    rest = []
    for c in (rec.get("Contacts") or {}).get("records") or []:
        if not (c.get("Name") or "").strip():
            continue
        e = entry(c)
        if e["name"].casefold() in seen:
            continue
        seen.add(e["name"].casefold())
        rest.append(e)

    # Stable sort, so current staff keep Salesforce's order and ex-staff fall
    # to the back without being hidden.
    return head + sorted(rest, key=lambda e: e["former"])
```

- [ ] **Step 4: Add the key to `map_account()`**

Directly after the `buyerName` line added in Task 2:

```python
        "buyerName": _buyer_name(rec),
        # Rep-only pick list for that field, rendered as chips under it. The
        # frontend hands customers an empty list — see App.jsx's isRepFilled.
        "contacts": _account_contacts(rec),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_mapping.py -q
```

Expected: `27 passed`.

- [ ] **Step 6: Confirm nothing else regressed**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest -q 2>&1 | tail -3
```

Expected: `17 failed, 189 passed, 1 skipped`.

- [ ] **Step 7: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add backend/app/salesforce/mapping.py backend/tests/test_account_mapping.py
git commit -m "feat: expose the account's contacts for the rep buyer picker"
```

---

## Task 4: `find_accounts()` asks Salesforce for the contacts

**Files:**
- Modify: `backend/app/salesforce/client.py:470`
- Test: `backend/tests/test_account_query.py` (create)

Without this task both helpers see nothing in production — the fields they read
are not in the query yet.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_account_query.py`:

```python
"""The buyer-lookup SOQL asks for what map_account() needs.

The mapping helpers read ContactBuying__r and the Contacts child subquery, so
if the query stops selecting them the autofill and the rep picker silently go
empty for every account. That failure is invisible in a mapping unit test,
hence this one.
"""
from unittest.mock import patch

from app.salesforce import client


def _run_lookup(**kwargs):
    """Capture the SOQL find_accounts() builds, without touching Salesforce."""
    with patch.object(client, "query_all", return_value=[]) as q:
        client.find_accounts(**kwargs)
    return q.call_args[0][0]


def test_query_selects_the_buying_contact_name():
    assert "ContactBuying__r.Name" in _run_lookup(email="buyer@apied.com")


def test_query_selects_the_buying_contact_title():
    assert "ContactBuying__r.Title" in _run_lookup(email="buyer@apied.com")


def test_query_includes_the_related_contacts_subquery():
    assert "(SELECT Name, Title FROM Contacts ORDER BY Name)" in _run_lookup(email="buyer@apied.com")


def test_subquery_sits_inside_the_select_clause():
    """A child subquery is only legal between SELECT and FROM."""
    soql = _run_lookup(name="A PIED")
    assert soql.index("(SELECT Name, Title FROM Contacts ORDER BY Name)") < soql.index(" FROM Account")


def test_admin_lookup_gets_the_same_fields():
    """The admin account picker uses include_excluded=True and must not lose
    the buyer name."""
    soql = _run_lookup(account_id="0012v00000AbCdEAAV", include_excluded=True)
    assert "ContactBuying__r.Name" in soql
    assert "(SELECT Name, Title FROM Contacts ORDER BY Name)" in soql
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_query.py -q
```

Expected: `3 failed, 2 passed`. The three subquery assertions fail
(`test_subquery_sits_inside_the_select_clause` fails with
`ValueError: substring not found`). The two `ContactBuying__r` assertions
already pass — Task 1 Step 4 put those fields in `ACCOUNT_FIELDS`. They stay as
regression guards.

- [ ] **Step 3: Append the subquery to the SELECT**

In `backend/app/salesforce/client.py`, inside `find_accounts()`, change line 470:

```python
    fields = ", ".join(mapping.ACCOUNT_FIELDS)
```

to:

```python
    # The child subquery is not a scalar field, so it lives outside
    # ACCOUNT_FIELDS; it must still land inside the SELECT clause, where SOQL
    # requires it. Related contacts feed both the buyer-name fallback and the
    # rep's contact picker.
    fields = ", ".join((*mapping.ACCOUNT_FIELDS, mapping.ACCOUNT_CONTACTS_SUBQUERY))
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest tests/test_account_query.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Verify the SOQL against the real org**

The tests above prove the string is built; only Salesforce can prove it parses.
Requires a filled-in `.env` at the repo root.

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 - <<'PY'
from pathlib import Path
import os
for line in Path("../.env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
from app.salesforce import client, mapping
for store in ("BIRCH", "URBAN OUTFITTERS UK LTD"):
    for rec in client.find_accounts(name=store, include_excluded=True):
        m = mapping.map_account(rec)
        print(f"{m['name']!r} -> buyerName={m['buyerName']!r}")
        for c in m["contacts"]:
            print(f"      {c}")
PY
```

Expected: `BIRCH` prefills `Kathleen Belavitch` with her in the contact list;
`URBAN OUTFITTERS UK LTD` prefills `None` and lists six contacts with
Emma Hopkin, Helen Webster and Imogen Roberts marked `'former': True` and
ordered last.

If it raises `MALFORMED_QUERY`, the subquery landed outside the SELECT clause —
re-check Step 3.

- [ ] **Step 6: Confirm the whole suite**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/backend
python3 -m pytest -q 2>&1 | tail -3
```

Expected: `17 failed, 194 passed, 1 skipped`.

- [ ] **Step 7: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add backend/app/salesforce/client.py backend/tests/test_account_query.py
git commit -m "feat: select the buying contact and account contacts in the lookup query"
```

---

## Task 5: The form prefills the field

**Files:**
- Modify: `frontend/src/App.jsx:180-181`

- [ ] **Step 1: Make the change**

In `applyAccount()`, replace the deliberately-blank line:

```js
    setBillToState({
      buyerName: '',
```

with:

```js
    setBillToState({
      // The account's buying contact from Salesforce. Blank when the org has
      // no unambiguous answer (~6% of accounts) — the buyer types it then, as
      // they did for every account before this. Never `name`: that is the
      // store, and filling a person field with it was the ef1c8e2 bug.
      buyerName: m.buyerName || '',
```

Leave the remaining lines of that object untouched.

- [ ] **Step 2: Confirm the frontend still builds**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add frontend/src/App.jsx
git commit -m "feat: autofill Bill To buyer name from the looked-up account"
```

---

## Task 6: The `BuyerContactPicker` component

**Files:**
- Create: `frontend/src/components/BuyerContactPicker.jsx`
- Modify: `frontend/src/index.css` (append at the end)

Built standalone here and wired up in Task 7, so a build break has one cause.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/BuyerContactPicker.jsx`:

```jsx
// The rep's shortcut for Bill To "Buyer name". Autofill names one person, but a
// store often has several and only a rep knows which one this order is for —
// Burlington Coat Factory keeps a sweater buyer and an accessory buyer, and
// Salesforce can flag only one of them as the buying contact.
//
// Rep-only. The gate lives in App.jsx (isRepFilled), which hands customers an
// empty list, so this component never has to know who is filling the form.
// Contacts arrive best-first with ex-staff last; rendering order is theirs.
export default function BuyerContactPicker({ contacts, selected, onPick }) {
  if (!contacts.length) return null

  const current = selected.trim().toLowerCase()

  return (
    <div className="buyer-contacts">
      <span className="buyer-contacts-label">Contacts on this account</span>
      <ul className="buyer-contacts-list">
        {contacts.map((c) => {
          const isSelected = c.name.toLowerCase() === current
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
```

- [ ] **Step 2: Add the styles**

Append to `frontend/src/index.css`:

```css
/* Rep-only buyer contact chips, under Bill To "Buyer name". */
.buyer-contacts {
  margin: -0.35rem 0 0.75rem;
}
.buyer-contacts-label {
  display: block;
  color: #6b6862;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.3rem;
}
.buyer-contacts-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.contact-chip {
  padding: 0.3rem 0.6rem;
  border: 1px solid #d8d4cc;
  border-radius: 999px;
  background: #fff;
  cursor: pointer;
  text-align: left;
  /* the global dark-button rule would make this text white on white */
  color: #1d1d1b;
  font: inherit;
  font-size: 0.82rem;
}
.contact-chip:hover {
  background: #f3f0ea;
}
.contact-chip.is-selected {
  border-color: #1d1d1b;
  background: #1d1d1b;
  color: #fff;
}
.contact-chip.is-former {
  opacity: 0.55;
}
.contact-title {
  display: block;
  font-size: 0.72rem;
  color: #6b6862;
  margin-top: 0.05rem;
}
.contact-chip.is-selected .contact-title {
  color: #d8d4cc;
}
```

- [ ] **Step 3: Confirm the build still passes**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/frontend
npm run build
```

Expected: build completes with no errors. (The component is unreferenced so
far; Vite will simply not include it.)

- [ ] **Step 4: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add frontend/src/components/BuyerContactPicker.jsx frontend/src/index.css
git commit -m "feat: add the buyer contact picker component"
```

---

## Task 7: Wire the picker into the form

**Files:**
- Modify: `frontend/src/App.jsx` (state near line 73; `applyAccount` at 180; `BuyerLookup` at 519; `Addresses` at 525)
- Modify: `frontend/src/components/Addresses.jsx:85` and the Bill To block at 140-147

- [ ] **Step 1: Hold the contact list in `App.jsx`**

Beside the other form state (near line 73), add:

```js
  // Contacts on the looked-up account, for the rep-only buyer picker. Empty
  // until a lookup succeeds, and emptied again when one matches nothing.
  const [accountContacts, setAccountContacts] = useState([])
```

- [ ] **Step 2: Fill it in `applyAccount()`**

In `applyAccount()`, directly after the `setForm(...)` call and before
`setBillToState(...)`:

```js
    setAccountContacts(m.contacts || [])
```

- [ ] **Step 3: Clear it when a lookup finds nothing**

At the `BuyerLookup` call site (around line 519), extend the existing
`onResult` handler:

```jsx
        onResult={(m) => {
          setLookupNoMatch(m.length === 0)
          // No account, no contacts — otherwise the previous store's people
          // stay on screen next to a form the rep is now filling from scratch.
          if (m.length === 0) setAccountContacts([])
        }}
```

- [ ] **Step 4: Pass the list to `Addresses`, gated on rep**

At the `Addresses` call site (around line 525), add one prop:

```jsx
        // Rep-only: a customer knows their own name and has no business seeing
        // their store's other staff. isRepFilled is a self-declared radio, the
        // same soft gate the conflict warning uses.
        buyerContacts={isRepFilled ? accountContacts : []}
```

- [ ] **Step 5: Render it in `Addresses.jsx`**

Add the import at the top of `frontend/src/components/Addresses.jsx`:

```jsx
import BuyerContactPicker from './BuyerContactPicker'
```

Change the signature on line 85 to accept the new prop:

```jsx
export default function Addresses({ billTo, shipTo, setBillTo, setShipTo, showLocationSearch = false, isNewAccount = false, buyerContacts = [] }) {
```

Then render the picker directly under the Buyer name field, replacing:

```jsx
        <Field
          label="Buyer name"
          value={billTo.buyerName}
          onChange={(v) => setBillTo('buyerName', v)}
          autoComplete="name"
          titleCaseOnBlur
          required
        />
```

with:

```jsx
        <Field
          label="Buyer name"
          value={billTo.buyerName}
          onChange={(v) => setBillTo('buyerName', v)}
          autoComplete="name"
          titleCaseOnBlur
          required
        />
        {/* Renders nothing for customers, or when the account has no contacts.
            The field stays free text either way — a rep can name someone
            Salesforce has never heard of. */}
        <BuyerContactPicker
          contacts={buyerContacts}
          selected={billTo.buyerName}
          onPick={(name) => setBillTo('buyerName', name)}
        />
```

- [ ] **Step 6: Confirm the build**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry/frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 7: Verify in the running app**

Use the project's `verify` skill (`.claude/skills/verify/SKILL.md`) to launch the
form, then walk both roles.

**As Sales Representative:**

1. Search `BIRCH` in **Account → Find your Account**.
2. **Bill To → Buyer name** shows `Kathleen Belavitch`; **Account Name (store)**
   still shows `BIRCH`. They must not be the same value.
3. A chip row appears under the field with `Kathleen Belavitch` highlighted.
4. Search `BURLINGTON COAT FACTORY`. Buyer name is blank, six chips appear.
   Click `Kara Shute — accessory buyer`; the field fills with `Kara Shute` and
   that chip becomes the selected one.
5. Type over the field by hand — it stays editable and no chip is highlighted.
6. Search `URBAN OUTFITTERS UK LTD`. Contacts titled *no longer* render greyed
   and sit at the end of the row.
7. Search a store with no contacts (`AZALEA`, San Francisco). No chip row at
   all, and the address fields still fill.

**As Customer:** restart, choose **Customer**, search `BURLINGTON COAT FACTORY`.
No chip row appears, and Buyer name behaves exactly as it does today.

- [ ] **Step 8: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add frontend/src/App.jsx frontend/src/components/Addresses.jsx
git commit -m "feat: let reps pick the buyer from the account's contacts"
```

---

## Task 8: Record the decision in the docs

**Files:**
- Modify: `docs/architecture.md:93`

- [ ] **Step 1: Update the field note**

`docs/architecture.md:93` currently lists `ContactBuying__c` as
"(reference to buying contact)" among fields **not used in v1**. That is no
longer true. Move it out of that list and document it, matching the surrounding
style:

```markdown
  - `ContactBuying__c` (reference to the buying Contact) — **USED**: the buyer
    lookup selects `ContactBuying__r.Name` to prefill Bill To "Buyer name", and
    a `(SELECT Name, Title FROM Contacts ORDER BY Name)` subquery feeds the rep-only contact
    picker under that field. `ContactBuyingEmail__c` is a formula over this same
    contact's Email, so the account's lookup key and its buyer name name the
    same person. Set on 4,731 of 5,059 wholesale accounts (2026-08-20) — but it
    is a plain lookup, so 25 accounts point at a contact belonging to a
    different account. Accounts without it fall back to a sole related Contact,
    and otherwise leave the field blank rather than guess.
    See `docs/superpowers/specs/2026-08-20-buyer-name-autofill-design.md`.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/webadmin/Automation/wholesale-order-entry
git add docs/architecture.md
git commit -m "docs: record ContactBuying__c as the buyer-name source"
```

---

## Done when

- [ ] `python3 -m pytest -q` from `backend/` reports `17 failed, 194 passed, 1 skipped` — the 17 being the untouched pre-existing failures.
- [ ] `npm run build` in `frontend/` succeeds.
- [ ] A rep looking up `BIRCH` sees Buyer name prefilled with `Kathleen Belavitch` and a matching selected chip.
- [ ] A rep looking up `BURLINGTON COAT FACTORY` sees a blank field and can fill it in one click from six chips.
- [ ] A rep looking up `URBAN OUTFITTERS UK LTD` sees ex-staff greyed and last.
- [ ] A **customer** looking up the same accounts sees no chips at all.
- [ ] The buyer lookup still issues exactly one Salesforce query per lookup.
