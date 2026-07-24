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

# Free-text special handling notes on the account (textarea). Shown to PPIC on
# the admin page; empty for new/unmatched accounts.
SPECIAL_INSTRUCTIONS = "Special_Instructions__c"

# Who wrote the order: picklist on the (managed-package) sales order object.
# Source for the Internal Use "Order written by" / "Split with" dropdowns.
SALES_ORDER = "kugo2p__SalesOrder__c"
WRITTEN_BY = "Written_By__c"

# ------------------------------------- Kugamon order push (Accept -> SF Draft)
# Header (kugo2p__SalesOrder__c) + lines (kugo2p__SalesOrderProductLine__c),
# all createable-verified 2026-07-23. Name/Status are NOT createable (auto).
SALES_ORDER_PRICEBOOK = "kugo2p__Pricebook2Id__c"
SALES_ORDER_BILLTONAME = "kugo2p__BillToName__c"
SALES_ORDER_WAREHOUSE = "kugo2p__Warehouse__c"
SALES_ORDER_START_SHIP = "Start_Ship_Date__c"
# Org default warehouse "000 - Bali" (~59k orders). Per-store warehouses for the
# rare >24/SKU case are left to the team to switch on the Draft (spec decision).
WAREHOUSE_BALI_ID = "a0p900000008hZlAAI"
SALES_ORDER_LINE = "kugo2p__SalesOrderProductLine__c"
SALES_ORDER_LINE_ORDER = "kugo2p__SalesOrder__c"  # parent lookup on the line
# NB: the line's Product field references Kugamon's product-detail record, NOT
# Product2. We store Product2 ids, so translate Product2 -> detail via the
# detail's ReferenceProduct lookup before creating lines (1 detail per Product2).
SALES_ORDER_LINE_PRODUCT = "kugo2p__Product__c"
SALES_ORDER_LINE_QTY = "kugo2p__Quantity__c"
KUGAMON_PRODUCT_DETAIL = "kugo2p__AdditionalProductDetail__c"
KUGAMON_DETAIL_REFERENCE_PRODUCT = "kugo2p__ReferenceProduct__c"

# Nearby-stockist conflict check (GET /api/accounts/nearby). Shipping geocodes
# are Salesforce-populated (verified 2026-07-17: 4,930/6,467 accounts, accuracy
# Address/NearAddress); BillingLatitude is unpopulated org-wide.
# Candidates are limited to accounts with recent order history via the
# sales order object's account lookup + business order date.
SALES_ORDER_ACCOUNT = "kugo2p__Account__c"
SALES_ORDER_DATE = "kugo2p__OrderDate__c"
# Salesforce "Order Name" (e.g. "F26 SWEATERS 11/01 - 11/20"); distinct from
# the record Name, which is the auto-numbered order number (SO-...).
SALES_ORDER_NAME = "kugo2p__OrderName__c"
ACCOUNT_TYPE = "Type"
# Accounts with these Rank__c values are not active stockists and never
# count as conflicts (decision 2026-07-18). Accounts with no rank still count.
RANK = "Rank__c"
EXCLUDED_RANKS = (
    "ZZ - No Booking",
    "Z - Inactive",
    "E - No Marketing",
    "X - Conflict",
    "OOB - Out of Business",
    "NGF - Not Going Forward",
)
WHOLESALE_TYPE = "Wholesale"
SHIPPING_LAT = "ShippingLatitude"
SHIPPING_LNG = "ShippingLongitude"
NEARBY_ACCOUNT_FIELDS = ("Id", "Name", "ShippingCity", "ShippingState", SHIPPING_LAT, SHIPPING_LNG)

# ------------------------------------------- Account create (new web accounts)
# All confirmed against the org via describe on 2026-07-23. New wholesale stores
# are BUSINESS accounts (person-account org, but a store is a business). Buyer
# is a Contact on the account (ContactBuying__c / ContactBuyingEmail__c is a
# non-createable rollup) — NOT created here; buyer details go into Description.
BUSINESS_ACCOUNT_RECORD_TYPE_ID = "01290000000gohtAAA"
TAX_ID_NUMBER = "Tax_ID_Number__c"
AIR_VS_SEA = "AIR_VS_SEA__c"
INTERNAL_REP = "Internal_Rep__c"  # lookup to User
# Standing defaults for a new web account (constants, not collected on the form):
INTERNAL_REP_USER_ID = "0052v00000jF9TGAA0"  # Christine Poveda (active User)
AIR_VS_SEA_NEW_ACCOUNT = "New Account - review at 6 month anniversary"
RANK_NEW_ACCOUNT = "C - $2,000+ / Monthly / All Mktg"

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
    SALES_TERRITORY,
    SPECIAL_INSTRUCTIONS,
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


def map_nearby_account(rec: dict[str, Any]) -> dict[str, Any]:
    """Salesforce Account record -> conflict-check candidate."""
    return {
        "accountId": rec["Id"],
        "name": rec.get("Name"),
        "cityState": _city_state(rec.get("ShippingCity"), rec.get("ShippingState")),
        "lastOrder": rec.get("lastOrderDate"),
        "lastOrderNumber": rec.get("lastOrderNumber"),
        "lastOrderName": rec.get("lastOrderName"),
        "lat": rec[SHIPPING_LAT],
        "lng": rec[SHIPPING_LNG],
    }


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
        "salesTerritory": rec.get(SALES_TERRITORY),
        "specialInstructions": rec.get(SPECIAL_INSTRUCTIONS),
        "certificateOnFile": _certificate_on_file(rec),
    }


def _split_city_state(value: str | None) -> tuple[str, str]:
    """'Los Angeles, CA' -> ('Los Angeles', 'CA'). No comma -> (value, '')."""
    if not value:
        return "", ""
    if "," in value:
        city, state = value.rsplit(",", 1)
        return city.strip(), state.strip()
    return value.strip(), ""


def build_account_create_payload(order: Any) -> dict[str, Any]:
    """Map a submitted (new-account) order to Salesforce Account create fields.

    Business account: Name is the store, RecordType is Business, Type is
    Wholesale. Store address == buyer address (first order's buyer is the store
    owner). Only fields confirmed createable are set; ContactBuyingEmail__c is a
    non-createable rollup, so the buyer's name/email/phone go into Description
    for the team to create/link the Contact. Blank values are dropped so we
    never overwrite org defaults with empty strings.
    """
    bill_city, bill_state = _split_city_state(order.bill_city_state)
    ship_city, ship_state = _split_city_state(order.ship_city_state)

    buyer_bits = [
        bit
        for bit in (
            f"Buyer: {order.buyer_name}" if order.buyer_name else "",
            f"Email: {order.ship_email}" if order.ship_email else "",
            f"Phone: {order.tel}" if order.tel else "",
        )
        if bit
    ]

    payload: dict[str, Any] = {
        "Name": (order.account_name or "").strip(),
        "RecordTypeId": BUSINESS_ACCOUNT_RECORD_TYPE_ID,
        ACCOUNT_TYPE: WHOLESALE_TYPE,  # "Type" = "Wholesale"
        INTERNAL_REP: INTERNAL_REP_USER_ID,  # Christine Poveda
        AIR_VS_SEA: AIR_VS_SEA_NEW_ACCOUNT,
        RANK: RANK_NEW_ACCOUNT,
        "BillingStreet": order.bill_street or "",
        "BillingCity": bill_city,
        "BillingState": bill_state,
        "BillingPostalCode": order.bill_zip or "",
        "ShippingStreet": order.ship_street or "",
        "ShippingCity": ship_city,
        "ShippingState": ship_state,
        "ShippingPostalCode": order.ship_zip or "",
        "Phone": order.tel or "",
        TAX_ID_NUMBER: order.resale_tax_id or "",
        SALES_TERRITORY: order.sales_territory or "",
        "Description": " | ".join(buyer_bits),
    }
    return {k: v for k, v in payload.items() if v not in ("", None)}


# Ship window looks like "8/1-30" or "12/1-10"; the start is month/first-day.
_SHIP_WINDOW_START_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})")


def start_ship_date(ship_window: str | None, season_code: str | None) -> str | None:
    """'8/1-30' + season 'F26' -> '2026-08-01' (ISO). None if unparseable.

    The year comes from the season code (F26/S27 -> 2026/2027); the window only
    carries month/day. Good enough for a Draft the team reviews.
    """
    m = _SHIP_WINDOW_START_RE.match(ship_window or "")
    s = _SEASON_CODE_RE.match((season_code or "").strip())
    if not m or not s:
        return None
    try:
        return date(2000 + int(s.group(2)), int(m.group(1)), int(m.group(2))).isoformat()
    except ValueError:
        return None


def build_sales_order_header(order: Any, pricebook_id: str) -> dict[str, Any]:
    """Order -> kugo2p__SalesOrder__c create fields. Name/Status/totals are left
    to Kugamon; Written_By is set for rep orders only (empty for direct)."""
    header: dict[str, Any] = {
        SALES_ORDER_ACCOUNT: order.sf_account_id,
        SALES_ORDER_PRICEBOOK: pricebook_id,
        SALES_ORDER_BILLTONAME: order.account_name or "",
        SALES_ORDER_WAREHOUSE: WAREHOUSE_BALI_ID,
    }
    ship_date = start_ship_date(order.ship_window, order.season_code)
    if ship_date:
        header[SALES_ORDER_START_SHIP] = ship_date
    # Rep orders credit the writer; direct/customer orders leave it empty
    # (decision 2026-07-22). The picklist values are the same rep names.
    if order.filled_by == "rep" and order.order_written_by:
        header[WRITTEN_BY] = order.order_written_by
    return {k: v for k, v in header.items() if v not in ("", None)}


def build_sales_order_lines(order: Any) -> list[dict[str, Any]]:
    """Order items -> one line per size with qty > 0 (product + quantity only;
    Kugamon prices from the header's price book)."""
    lines: list[dict[str, Any]] = []
    for item in order.items:
        for product_id, qty in (
            (item.sf_product_id_xs, item.qty_xs),
            (item.sf_product_id_sm, item.qty_sm),
            (item.sf_product_id_ml, item.qty_ml),
        ):
            if product_id and qty:
                lines.append({SALES_ORDER_LINE_PRODUCT: product_id, SALES_ORDER_LINE_QTY: qty})
    return lines


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
