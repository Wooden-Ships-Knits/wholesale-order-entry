"""automatic chasers for unsigned orders: reminder counter + last-sent stamp

Revision ID: 0016_signature_reminders
Revises: 0015_signature_link
Create Date: 2026-08-06

An unsigned order is chased automatically at the ages in
settings.signature_reminder_hours (48h and 96h after the first request).

signature_reminders_sent is a COUNT, not a timestamp: it indexes into that
schedule, so it answers "which reminder is next" even if the schedule is
later changed or extended. A pair of timestamps would have to be re-derived
against the new schedule and would double-send the moment one was added.

NOT NULL DEFAULT 0 so orders that predate this — including any with a live
link right now — start at the beginning of the schedule rather than at NULL,
which would compare false against every threshold and never chase.

signature_reminded_at is for the admin table and the logs: when the last
chaser actually left. Nothing branches on it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_signature_reminders"
down_revision: Union[str, None] = "0015_signature_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column(
            "signature_reminders_sent",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("signature_reminded_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("orders", "signature_reminded_at")
    op.drop_column("orders", "signature_reminders_sent")
