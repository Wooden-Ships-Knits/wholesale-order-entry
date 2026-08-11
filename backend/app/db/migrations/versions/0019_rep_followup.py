"""day-6 nudge to the rep when their order is still unsigned

Revision ID: 0019_rep_followup
Revises: 0018_signature_bounce
Create Date: 2026-08-10

The buyer already gets chased on days 2, 5, 15, 22 and 29. This is the one
email that goes to the REP instead: by day six the automatic nudges clearly
are not working, and a phone call from the person who wrote the order is worth
more than a sixth email to the same inbox.

A nullable timestamp rather than a counter or a bool: there is exactly one of
these per order, "when did it go" is worth answering, and nulling it re-arms
the nudge if a request is ever sent afresh.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_rep_followup"
down_revision: Union[str, None] = "0018_signature_bounce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("rep_followup_sent_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("orders", "rep_followup_sent_at")
