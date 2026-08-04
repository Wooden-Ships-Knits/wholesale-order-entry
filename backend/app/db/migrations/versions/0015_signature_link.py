"""buyer signature-by-link: token, recipient, and pre-edit totals

Revision ID: 0015_signature_link
Revises: 0014_merge_heads
Create Date: 2026-08-01

The admin sends the buyer a link from the order table (same draft-then-send
flow as the conflict and tax-cert emails). The buyer opens it, may adjust
quantities, and signs. Signing writes signature_name and stamps
signature_signed_at, and the token is spent.

No new order status: an unsigned order is a normal 'submitted' order whose
signature is outstanding, exactly as an unanswered conflict email is. The
admin column reads these timestamps, not a state machine.

signature_token is a bearer credential — whoever holds the URL can edit and
sign — so it is random (never the order id, which appears in admin URLs, log
lines and PDF filenames), single-use, and time-limited. UNIQUE so a lookup
can't ambiguously match; Postgres exempts NULL from UNIQUE, which is what
lets every never-sent and already-signed order sit at NULL together.

orig_total_* snapshot the order as the rep wrote it, taken when the link is
first sent. Without them a buyer's edit is invisible: the rep's copy and the
accepted order would silently disagree about what was ordered.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_signature_link"
down_revision: Union[str, None] = "0014_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Where the link was sent. Persisted so it can be re-sent without the
    # admin retyping the address, and as a record of who was asked to sign.
    op.add_column("orders", sa.Column("signature_email", sa.Text()))
    op.add_column("orders", sa.Column("signature_token", sa.Text()))
    op.add_column(
        "orders", sa.Column("signature_token_expires_at", sa.DateTime(timezone=True))
    )
    # null = no signature was ever requested for this order.
    op.add_column(
        "orders", sa.Column("signature_requested_at", sa.DateTime(timezone=True))
    )
    # Distinct from signature_name, which a rep-filled order already has:
    # this is set only by the buyer signing through the link.
    op.add_column(
        "orders", sa.Column("signature_signed_at", sa.DateTime(timezone=True))
    )
    op.add_column("orders", sa.Column("orig_total_qty", sa.Integer()))
    op.add_column("orders", sa.Column("orig_total_amount", sa.Numeric(12, 2)))
    op.create_index(
        "ix_orders_signature_token", "orders", ["signature_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_orders_signature_token", table_name="orders")
    op.drop_column("orders", "orig_total_amount")
    op.drop_column("orders", "orig_total_qty")
    op.drop_column("orders", "signature_signed_at")
    op.drop_column("orders", "signature_requested_at")
    op.drop_column("orders", "signature_token_expires_at")
    op.drop_column("orders", "signature_token")
    op.drop_column("orders", "signature_email")
