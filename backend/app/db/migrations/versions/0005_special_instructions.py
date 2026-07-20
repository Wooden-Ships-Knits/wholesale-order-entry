"""store the account's Salesforce special instructions on the order

Revision ID: 0005_special_instructions
Revises: 0004_sales_territory
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_special_instructions"
down_revision: Union[str, None] = "0004_sales_territory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("special_instructions", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "special_instructions")
