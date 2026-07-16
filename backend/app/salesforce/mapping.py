"""Single source of truth for Salesforce object/field names and data mapping.

All object/field names were confirmed against the real org on 2026-07-14
(see docs/architecture.md §3.2). If a name changes in Salesforce, this is
the only file that should need editing.
"""
import re
from datetime import date
from typing import Any

# ---------------------------------------------------------------- objects
ACCOUNT = "Account"
PRODUCT2 = "Product2"
PRICEBOOK2 = "Pricebook2"
PRICEBOOK_ENTRY = "PricebookEntry"

# ------------------------------------------------- Account (person-account org)
# Canonical buyer-lookup key (decision 2026-07-14).
ACCOUNT_LOOKUP_EMAIL = "ContactBuyingEmail__c"

# Sales rep on the account; also the source for the Internal Use "Rep" picklist.
SALESPERSON = "Salesperson__c"

# Territory-and-rep label, e.g. "Midwest - Aviva Landin". Free text on Account
# (not a picklist), so the option list is the distinct values actually in use.
SALES_TERRITORY = "SalesTerritory__c"

# Who wrote the order: picklist on the (managed-package) sales order object.
# Source for the Internal Use "Order written by" / "Split with" dropdowns.
SALES_ORDER = "kugo2p__SalesOrder__c"
WRITTEN_BY = "Written_By__c"

ACCOUNT_FIELDS = (
    "Id",
    "Name",
    "IsPersonAccount",
    "BillingStreet",
    "BillingCity",
    "BillingState",
    "BillingPostalCode",
    "ShippingStreet",
    "ShippingCity",
    "ShippingState",
    "ShippingPostalCode",
    "Phone",
    "Fax",
    ACCOUNT_LOOKUP_EMAIL,
    "Tax_ID_Number__c",
    "Tax_ID_Verified__c",
    "Tax_ID_Expires__c",
    SALESPERSON,
)

# ------------------------------------------------------- seasons / price books
# One wholesale price book per season, named "<season> Wholesale"
# (e.g. "F26 Wholesale") — confirmed: the F26 book contains exactly the
# K57-prefixed products.
WHOLESALE_BOOK_SUFFIX = " Wholesale"

# Season code embedded in ProductCode: leading letters + 2-digit number,
# e.g. K57A5W191 -> 57. Odd -> Fall, even -> Spring; year = floor(n/2) - 2
# (K57 = F26, K58 = S27).
_PRODUCT_CODE_SEASON_RE = re.compile(r"^[A-Z]+(\d{2})")
_SEASON_CODE_RE = re.compile(r"^([FS])(\d{2})$")

# The order form has exactly these size columns (PRD §5.5; decision 2026-07-14:
# X/L SKUs exist in the org but are NOT orderable on the web form).
SIZES = ("X/S", "S/M", "M/L")
SIZE_KEYS = {"X/S": "xs", "S/M": "sm", "M/L": "ml"}


def season_from_pricebook_name(book_name: str) -> str | None:
    """'F26 Wholesale' -> 'F26'; None if the name isn't a season book."""
    if not book_name.endswith(WHOLESALE_BOOK_SUFFIX):
        return None
    code = book_name[: -len(WHOLESALE_BOOK_SUFFIX)].strip()
    return code if _SEASON_CODE_RE.match(code) else None


def pricebook_name_for_season(season_code: str) -> str:
    return f"{season_code}{WHOLESALE_BOOK_SUFFIX}"


def season_label(season_code: str) -> str:
    """'F26' -> 'Fall 2026'."""
    m = _SEASON_CODE_RE.match(season_code)
    if not m:
        return season_code
    word = "Fall" if m.group(1) == "F" else "Spring"
    return f"{word} 20{m.group(2)}"


def season_sort_key(season_code: str) -> int:
    """Chronological key: Spring precedes Fall within a year."""
    m = _SEASON_CODE_RE.match(season_code)
    if not m:
        return -1
    return int(m.group(2)) * 2 + (1 if m.group(1) == "F" else 0)


def season_number_from_product_code(product_code: str) -> int | None:
    """'K57A5W191' -> 57."""
    m = _PRODUCT_CODE_SEASON_RE.match(product_code or "")
    return int(m.group(1)) if m else None


def season_code_from_number(n: int) -> str:
    """57 -> 'F26', 58 -> 'S27' (odd = Fall, even = Spring, year = n//2 - 2)."""
    return f"{'F' if n % 2 else 'S'}{n // 2 - 2:02d}"


def parse_product_name(name: str) -> tuple[str, str, str] | None:
    """'SKI PULLOVER-NIGHT/BONFIRE-X/S' -> ('SKI PULLOVER', 'NIGHT/BONFIRE', 'X/S').

    Parsed from the right: colors/sizes contain '/', styles may contain '-'.
    Returns None if the name doesn't have three '-'-separated segments.
    """
    parts = name.rsplit("-", 2)
    if len(parts) != 3:
        return None
    style, color, size = (p.strip() for p in parts)
    return style, color, size


def _city_state(city: str | None, state: str | None) -> str:
    return ", ".join(p for p in (city, state) if p)


def _certificate_on_file(rec: dict[str, Any]) -> bool:
    """Derived from Tax_ID_Verified__c, invalidated by a past Tax_ID_Expires__c."""
    if not rec.get("Tax_ID_Verified__c"):
        return False
    expires = rec.get("Tax_ID_Expires__c")
    if expires:
        try:
            if date.fromisoformat(expires) < date.today():
                return False
        except ValueError:
            pass
    return True


def map_account(rec: dict[str, Any]) -> dict[str, Any]:
    """Salesforce Account record -> frontend autofill payload."""
    return {
        "accountId": rec["Id"],
        "name": rec.get("Name"),
        "billTo": {
            "street": rec.get("BillingStreet"),
            "cityState": _city_state(rec.get("BillingCity"), rec.get("BillingState")),
            "zip": rec.get("BillingPostalCode"),
            "tel": rec.get("Phone"),
            "fax": rec.get("Fax"),
        },
        "shipTo": {
            "street": rec.get("ShippingStreet"),
            "cityState": _city_state(rec.get("ShippingCity"), rec.get("ShippingState")),
            "zip": rec.get("ShippingPostalCode"),
        },
        "email": rec.get(ACCOUNT_LOOKUP_EMAIL),
        "resaleTaxId": rec.get("Tax_ID_Number__c"),
        "rep": rec.get("Salesperson__c"),
        "certificateOnFile": _certificate_on_file(rec),
    }


def group_products(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """PricebookEntry records -> form rows grouped by (style, color).

    Each row carries one Product2 id per orderable size column. Sizes outside
    SIZES (e.g. X/L, O/S) are counted in stats and skipped per the 2026-07-14
    decision.
    """
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    stats = {"entries": len(entries), "skipped_size": 0, "unparsed_name": 0, "price_conflicts": 0}

    for e in entries:
        parsed = parse_product_name(e["Product2"]["Name"])
        if parsed is None:
            stats["unparsed_name"] += 1
            continue
        style, color, size = parsed
        if size not in SIZE_KEYS:
            stats["skipped_size"] += 1
            continue

        row = rows.setdefault(
            (style, color),
            {
                "code": e.get("ProductCode"),
                "styleName": style,
                "color": color,
                "unitPrice": None,
                "sizes": {k: None for k in SIZE_KEYS.values()},
            },
        )
        row["sizes"][SIZE_KEYS[size]] = e["Product2Id"]

        price = e.get("UnitPrice")
        if row["unitPrice"] is None:
            row["unitPrice"] = price
        elif price is not None and price != row["unitPrice"]:
            stats["price_conflicts"] += 1
            row["unitPrice"] = max(row["unitPrice"], price)

    ordered = sorted(rows.values(), key=lambda r: (r["styleName"], r["color"]))
    return ordered, stats
