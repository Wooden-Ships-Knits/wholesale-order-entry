"""link the pushed Kugamon sales order back to our order

Revision ID: 0009_sf_order
Revises: 0008_sf_account_created
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_sf_order"
down_revision: Union[str, None] = "0008_sf_account_created"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The created kugo2p__SalesOrder__c: id (idempotency anchor) + its
    # auto-number Name (e.g. SO-260721-0073266) for the team to find it.
    op.add_column("orders", sa.Column("sf_order_id", sa.Text()))
    op.add_column("orders", sa.Column("sf_order_number", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "sf_order_number")
    op.drop_column("orders", "sf_order_id")
