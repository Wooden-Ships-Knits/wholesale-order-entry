"""Turn submitted quantities into priced OrderItem rows.

Shared by the two paths that can set an order's lines:
  POST /api/orders          — the buyer or rep submitting the form
  POST /api/sign/{token}    — the buyer adjusting quantities before signing

Prices and Salesforce product ids are ALWAYS re-resolved from the season's
wholesale price book. Whatever the client sent is ignored. That is what makes
buyer-editable orders safe: the signing path can accept new quantities without
being able to influence what they cost.

Minimums are checked here too, so both paths enforce the same rules (PRD §6)
and no caller can forget to.
"""
import logging
from decimal import Decimal
from typing import Any

from app.db.models import OrderItem
from app.salesforce import client, mapping
from app.validation.order_minimum import validate_minimums

logger = logging.getLogger(__name__)


def build(
    season: str, items: list[Any], *, enforce_minimums: bool = True
) -> tuple[list[OrderItem], int, Decimal, list[dict]]:
    """(order_items, total_qty, total_amount, errors) for one season's lines.

    `items` are schema objects with .style_name, .color, .qty_xs/_sm/_ml and
    .pieces — already filtered to those with a quantity. A non-empty `errors`
    means nothing should be persisted; the lists returned alongside it are
    incomplete by design.

    enforce_minimums=False is for SAVING A DRAFT, where half a basket is the
    normal state and refusing to store it defeats the point. It relaxes only
    the order-shape rules (18 pieces, 4 per style, 2 per SKU, and "no items at
    all"); an unknown product is still an error, because there is no line to
    build from it. Signing always enforces — CLAUDE.md rule 5 puts the
    authority server-side, and a draft is not a submission.
    """
    errors: list[dict] = []

    if enforce_minimums:
        if not items:
            errors.append({"code": "no_items", "message": "The order has no quantities."})
        errors.extend(validate_minimums(items))
    if errors:
        return [], 0, Decimal("0"), errors
    if not items:
        return [], 0, Decimal("0"), []

    # Resolve the season's wholesale price book — authoritative prices + ids.
    books = {
        mapping.season_from_pricebook_name(b["Name"]): b
        for b in client.list_wholesale_pricebooks()
    }
    book = books.get(season)
    if book is None:
        return [], 0, Decimal("0"), [
            {"code": "season", "message": f"Unknown season {season}."}
        ]
    rows, _stats = mapping.group_products(client.get_pricebook_entries(book["Id"]))
    catalog = {(r["styleName"], r["color"]): r for r in rows}

    order_items: list[OrderItem] = []
    total_qty = 0
    total_amount = Decimal("0")
    for item in items:
        row = catalog.get((item.style_name, item.color))
        if row is None:
            errors.append(
                {
                    "code": "unknown_product",
                    "style": item.style_name,
                    "color": item.color,
                    "message": f'"{item.style_name} — {item.color}" is not in the {season} wholesale catalog.',
                }
            )
            continue
        unit_price = Decimal(str(row["unitPrice"] or 0)).quantize(Decimal("0.01"))
        line_qty = item.pieces
        line_total = (unit_price * line_qty).quantize(Decimal("0.01"))
        total_qty += line_qty
        total_amount += line_total
        order_items.append(
            OrderItem(
                sf_product_id_xs=row["sizes"]["xs"] if item.qty_xs else None,
                sf_product_id_sm=row["sizes"]["sm"] if item.qty_sm else None,
                sf_product_id_ml=row["sizes"]["ml"] if item.qty_ml else None,
                code=row["code"],
                style_name=item.style_name,
                color=item.color,
                qty_xs=item.qty_xs,
                qty_sm=item.qty_sm,
                qty_ml=item.qty_ml,
                line_qty=line_qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    if errors:
        return [], 0, Decimal("0"), errors
    return order_items, total_qty, total_amount, []
