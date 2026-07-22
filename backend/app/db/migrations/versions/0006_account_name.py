"""store the account/store name separately from the Bill To buyer person

Revision ID: 0006_account_name
Revises: 0005_special_instructions
Create Date: 2026-07-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_account_name"
down_revision: Union[str, None] = "0005_special_instructions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("account_name", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "account_name")
