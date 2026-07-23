"""track when the admin sent the conflict / tax-cert email for an order

Revision ID: 0010_email_sent_at
Revises: 0009_sf_order
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_email_sent_at"
down_revision: Union[str, None] = "0009_sf_order"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # When set, the admin has sent the corresponding email for this order from
    # /admin, so the button shows "Sent ✓" instead of "Generate email" — and
    # that survives a page reload. null = not sent yet.
    op.add_column("orders", sa.Column("conflict_email_sent_at", sa.DateTime(timezone=True)))
    op.add_column("orders", sa.Column("tax_cert_email_sent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("orders", "tax_cert_email_sent_at")
    op.drop_column("orders", "conflict_email_sent_at")
