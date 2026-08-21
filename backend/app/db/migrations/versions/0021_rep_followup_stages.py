"""rep nudges become a sequence (days 6, 21, 31) instead of one

Revision ID: 0021_rep_followup_stages
Revises: 0020_prospects
Create Date: 2026-08-19

The rep used to get one nudge on day 6 and nothing after. Wooden Ships added
two escalations, on days 21 and 31, with different wording — by then the message
is no longer "email isn't working" but "we asked you ten days ago".

One nullable timestamp cannot express "two of three sent", so this adds a
counter alongside it, exactly as the buyer's chasers already work:
signature_reminders_sent is the cursor, signature_reminded_at is the display.

BACKFILL MATTERS. Orders that already had the day-6 nudge carry a
rep_followup_sent_at but would start at counter 0, so the sweep would send
them day 6 a second time. Setting the counter to 1 for those rows makes the
next one they receive the day-21 escalation, which is correct.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_rep_followup_stages"
down_revision: Union[str, None] = "0020_prospects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "rep_followups_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        "UPDATE orders SET rep_followups_sent = 1 "
        "WHERE rep_followup_sent_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("orders", "rep_followups_sent")
