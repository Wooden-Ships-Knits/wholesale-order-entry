"""store the classifier's suggested conflict outcome + mark replies processed

Revision ID: 0013_conflict_ai_suggestion
Revises: 0012_inbound_replies
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_conflict_ai_suggestion"
down_revision: Union[str, None] = "0012_inbound_replies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AI suggestion on the order (a proposal a human confirms). outcome is
    # cleared | real_conflict | unclear; confidence is 0..1.
    op.add_column("orders", sa.Column("conflict_ai_outcome", sa.Text()))
    op.add_column("orders", sa.Column("conflict_ai_confidence", sa.Numeric(3, 2)))
    op.add_column("orders", sa.Column("conflict_ai_reason", sa.Text()))
    op.add_column("orders", sa.Column("conflict_ai_at", sa.DateTime(timezone=True)))
    # Marks a captured reply as classified so a re-poll doesn't re-run the model.
    op.add_column(
        "inbound_replies", sa.Column("processed_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("inbound_replies", "processed_at")
    op.drop_column("orders", "conflict_ai_at")
    op.drop_column("orders", "conflict_ai_reason")
    op.drop_column("orders", "conflict_ai_confidence")
    op.drop_column("orders", "conflict_ai_outcome")
