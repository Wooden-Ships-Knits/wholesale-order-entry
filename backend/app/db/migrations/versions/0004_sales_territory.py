"""store the account's Salesforce sales territory on the order

Revision ID: 0004_sales_territory
Revises: 0003_order_review
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_sales_territory"
down_revision: Union[str, None] = "0003_order_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("sales_territory", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "sales_territory")
