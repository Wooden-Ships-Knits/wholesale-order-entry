"""track when a new-account order's Salesforce Account was created from /admin

Revision ID: 0008_sf_account_created
Revises: 0007_order_copy_email
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_sf_account_created"
down_revision: Union[str, None] = "0007_order_copy_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # When set, the SF Business Account for this (new) order was created from
    # /admin. The created Account Id lands in the existing sf_account_id column.
    op.add_column("orders", sa.Column("sf_account_created_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("orders", "sf_account_created_at")
