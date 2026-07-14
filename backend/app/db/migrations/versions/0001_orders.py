"""orders + order_items (no card number / CVV columns — CLAUDE.md rule 1)

Revision ID: 0001_orders
Revises:
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_orders"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("season_code", sa.Text(), nullable=False),
        sa.Column("order_date", sa.Date()),
        sa.Column("part_ship_ok", sa.Boolean()),
        sa.Column("ship_window_note", sa.Text()),
        # bill to
        sa.Column("buyer_name", sa.Text()),
        sa.Column("bill_street", sa.Text()),
        sa.Column("bill_city_state", sa.Text()),
        sa.Column("bill_zip", sa.Text()),
        sa.Column("tel", sa.Text()),
        sa.Column("fax", sa.Text()),
        # ship to
        sa.Column("ship_email", sa.Text(), nullable=False),
        sa.Column("ship_street", sa.Text()),
        sa.Column("ship_city_state", sa.Text()),
        sa.Column("ship_zip", sa.Text()),
        sa.Column("resale_tax_id", sa.Text()),
        # payment — intentionally ONLY name + last4
        sa.Column("card_name", sa.Text()),
        sa.Column("card_last4", sa.Text()),
        # tax exemption
        sa.Column("cert_required_ack", sa.Boolean()),
        sa.Column("cert_sending_ack", sa.Boolean()),
        sa.Column("cert_on_file", sa.Boolean()),
        # signature / terms
        sa.Column("signature_name", sa.Text()),
        sa.Column("signature_date", sa.Date()),
        sa.Column("terms_accepted", sa.Boolean()),
        # internal use
        sa.Column("new_or_reorder", sa.Text()),
        sa.Column("account_status", sa.Text()),
        sa.Column("campaign", sa.Text()),
        sa.Column("po_number", sa.Text()),
        sa.Column("rep", sa.Text()),
        sa.Column("order_written_by", sa.Text()),
        sa.Column("split_with", sa.Text()),
        # salesforce link
        sa.Column("sf_account_id", sa.Text()),
        # totals / status
        sa.Column("total_qty", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sf_product_id_xs", sa.Text()),
        sa.Column("sf_product_id_sm", sa.Text()),
        sa.Column("sf_product_id_ml", sa.Text()),
        sa.Column("code", sa.Text()),
        sa.Column("style_name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("qty_xs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_sm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_ml", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("line_qty", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_table("orders")
