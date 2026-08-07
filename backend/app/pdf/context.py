"""Build the Jinja context for the order PDF from an Order row.

Extracted from routers/orders.py so the PDF can be re-rendered later from the
database alone — the buyer's signature arrives days after submit, via the
emailed signature link, and the PDF has to be redrawn to show it.

That re-render is only possible for the MASKED copy. The full card number
exists solely inside the submit request (rule 1: no card-number column), so
the encrypted admin copy can only ever be made at submit time. Everything
here comes from persisted columns, which is exactly why it is safe to call
again later.

The caller sets context["card"]. masked_card() below builds that value from
persisted columns only — last four digits, never a number. A full-card context
is assembled by the submit handler alone, from the request in memory.
"""
from typing import Any

from app.db.models import Order
from app.salesforce import mapping


def masked_card(order: Order) -> dict[str, Any]:
    """context["card"] for any copy that leaves the server.

    Built from stored columns, so there is no number to leak: card_last4,
    card_name and card_exp are the only card fields the DB holds (rule 1).
    Every masked render goes through here so the customer copy, the disk copy
    and any re-render show the same thing.
    """
    return {
        "name": order.card_name or None,
        "number": f"•••• {order.card_last4}" if order.card_last4 else None,
        "exp": order.card_exp or None,
        "full": False,
    }


def build(order: Order, *, created_at=None, items=None) -> dict[str, Any]:
    """Context for pdf/template.html.

    created_at: submit passes its own timestamp because the row hasn't been
    committed yet and created_at is a server default (still None in Python).
    items: same reason — pass the not-yet-flushed OrderItem list at submit;
    later callers let it default to the persisted relationship.
    """
    stamp = created_at or order.created_at
    lines = order.items if items is None else items
    return {
        "order": {
            "short_id": str(order.id)[:8],
            "season_code": order.season_code,
            "season_label": mapping.season_label(order.season_code),
            "order_date": order.order_date,
            "part_ship_ok": order.part_ship_ok,
            "ship_window_note": order.ship_window_note,
            "ship_window": order.ship_window,
            "filled_by": order.filled_by,
            "notes": order.notes,
            "payment_method": order.payment_method,
            "approval_before_charge": order.approval_before_charge,
            "cert_filename": order.cert_filename,
            "created_at": stamp.strftime("%Y-%m-%d %H:%M UTC") if stamp else "",
            # The store the order is for — Bill To / Ship To name on the PDF.
            # Distinct from buyer_name, which is the person placing it.
            "account_name": order.account_name,
            "buyer_name": order.buyer_name,
            "bill_street": order.bill_street,
            "bill_city_state": order.bill_city_state,
            "bill_zip": order.bill_zip,
            "tel": order.tel,
            "fax": order.fax,
            "ship_email": order.ship_email,
            "ship_street": order.ship_street,
            "ship_city_state": order.ship_city_state,
            "ship_zip": order.ship_zip,
            "resale_tax_id": order.resale_tax_id,
            "cert_required_ack": order.cert_required_ack,
            "cert_sending_ack": order.cert_sending_ack,
            "cert_on_file": order.cert_on_file,
            "signature_name": order.signature_name,
            "signature_date": order.signature_date,
            "terms_accepted": order.terms_accepted,
            "new_or_reorder": order.new_or_reorder,
            "account_status": order.account_status,
            "campaign": order.campaign,
            "po_number": order.po_number,
            "rep": order.rep,
            "order_written_by": order.order_written_by,
            # Re-derived for display: the columns are now structured (0016),
            # but the PDF still reads "Y — Name" / "N" as the team expects.
            "split_with": (
                f"Y — {order.split_with}" if order.split and order.split_with
                else "Y" if order.split
                else "N" if order.split is False
                else ""
            ),
            "sf_account_id": order.sf_account_id,
            "total_qty": order.total_qty,
            "total_amount": order.total_amount,
        },
        "items": [
            {
                "code": i.code,
                "style_name": i.style_name,
                "color": i.color,
                "qty_xs": i.qty_xs,
                "qty_sm": i.qty_sm,
                "qty_ml": i.qty_ml,
                "line_qty": i.line_qty,
                "unit_price": i.unit_price,
                "line_total": i.line_total,
            }
            for i in lines
        ],
        # Card block is the caller's job — never set here. CVV never appears.
        "card": None,
    }
