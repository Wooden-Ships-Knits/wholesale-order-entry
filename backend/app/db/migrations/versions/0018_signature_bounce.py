"""record a bounced signature request, so a dead address stops looking sent

Revision ID: 0018_signature_bounce
Revises: 0017_merge_heads
Create Date: 2026-08-10

mailer.send_email returning True only means the SMTP server ACCEPTED the
message. A wrong-but-syntactically-valid address ("molly@monkeesofhighpoint.com"
where no such mailbox exists) is accepted and then bounced minutes later by a
Delivery Status Notification to wholesale@.

Until now nothing read those. signature_requested_at was stamped, /admin showed
"Email Sent ✓ waiting for signature", and the five chasers fired for 30 days at
an address that could never receive them — while the rep was being told to
follow up with a customer who had heard nothing.

These two columns are set by the inbound poller when it recognises a DSN for an
order's signature address, and cleared whenever the request is sent again, so
correcting the address resets the state.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_signature_bounce"
down_revision: Union[str, None] = "0017_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("signature_bounced_at", sa.DateTime(timezone=True))
    )
    op.add_column("orders", sa.Column("signature_bounce_reason", sa.Text()))


def downgrade() -> None:
    op.drop_column("orders", "signature_bounce_reason")
    op.drop_column("orders", "signature_bounced_at")
