"""record the admin's outcome of a conflict inquiry (cleared / real conflict)

Revision ID: 0011_conflict_resolution
Revises: 0010_email_sent_at
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_conflict_resolution"
down_revision: Union[str, None] = "0010_email_sent_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # When conflict_resolved_at is set, the admin has recorded how a conflict
    # inquiry ended, so the row closes instead of sitting at "waiting". null =
    # still waiting for the rep. conflict_resolution is "cleared" (proceed) or
    # "real_conflict"; conflict_resolution_note is optional free text.
    op.add_column("orders", sa.Column("conflict_resolution", sa.Text()))
    op.add_column(
        "orders", sa.Column("conflict_resolved_at", sa.DateTime(timezone=True))
    )
    op.add_column("orders", sa.Column("conflict_resolution_note", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "conflict_resolution_note")
    op.drop_column("orders", "conflict_resolved_at")
    op.drop_column("orders", "conflict_resolution")
