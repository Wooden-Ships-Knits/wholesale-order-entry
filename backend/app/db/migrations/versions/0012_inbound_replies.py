"""capture inbound conflict replies correlated to their order

Revision ID: 0012_inbound_replies
Revises: 0011_conflict_resolution
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_inbound_replies"
down_revision: Union[str, None] = "0011_conflict_resolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbound_replies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Uuid(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("from_address", sa.Text()),
        sa.Column("subject", sa.Text()),
        sa.Column("snippet", sa.Text()),
        # Unique so a re-fetch of the same message can't create a duplicate row.
        sa.Column("message_id", sa.Text(), unique=True),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_inbound_replies_order_id", "inbound_replies", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_inbound_replies_order_id", table_name="inbound_replies")
    op.drop_table("inbound_replies")
