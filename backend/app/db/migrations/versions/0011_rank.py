"""store the account Rank__c at order time

Revision ID: 0011_rank
Revises: 0010_email_sent_at
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_rank"
down_revision: Union[str, None] = "0010_email_sent_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("rank", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "rank")
