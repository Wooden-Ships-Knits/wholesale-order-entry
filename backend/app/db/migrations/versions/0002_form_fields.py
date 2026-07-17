"""new form fields: ship window, filled-by, notes, payment method, coords, cert file

Revision ID: 0002_form_fields
Revises: 0001_orders
Create Date: 2026-07-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_form_fields"
down_revision: Union[str, None] = "0001_orders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("ship_window", sa.Text()),
        sa.Column("filled_by", sa.Text()),  # rep | customer
        sa.Column("notes", sa.Text()),
        sa.Column("payment_method", sa.Text()),  # link | card
        sa.Column("approval_before_charge", sa.Boolean()),
        # Google Places coordinates (optional)
        sa.Column("bill_lat", sa.Numeric(9, 6)),
        sa.Column("bill_lng", sa.Numeric(9, 6)),
        sa.Column("ship_lat", sa.Numeric(9, 6)),
        sa.Column("ship_lng", sa.Numeric(9, 6)),
        # uploaded tax-exemption certificate (file saved beside the order PDF)
        sa.Column("cert_filename", sa.Text()),
    ]


def upgrade() -> None:
    for col in _columns():
        op.add_column("orders", col)


def downgrade() -> None:
    for col in reversed(_columns()):
        op.drop_column("orders", col.name)
