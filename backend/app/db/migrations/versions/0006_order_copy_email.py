"""store the buyer's requested order-copy email on the order

Revision ID: 0006_order_copy_email
Revises: 0005_special_instructions
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_order_copy_email"
down_revision: Union[str, None] = "0005_special_instructions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("order_copy_email", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "order_copy_email")
