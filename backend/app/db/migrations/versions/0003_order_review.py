"""admin review fields: new-account flag, conflict verdict, accept/decline

Revision ID: 0003_order_review
Revises: 0002_form_fields
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_order_review"
down_revision: Union[str, None] = "0002_form_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> list[sa.Column]:
    return [
        # from the rep's Internal Use "New account / Existing" radio
        sa.Column("is_new_account", sa.Boolean()),
        # nearby-stockist conflict; null = not yet checked (not "no conflict")
        sa.Column("has_conflict", sa.Boolean()),
        # accept / decline review
        sa.Column("status_reason", sa.Text()),
        sa.Column("status_at", sa.DateTime(timezone=True)),
    ]


def upgrade() -> None:
    for col in _columns():
        op.add_column("orders", col)


def downgrade() -> None:
    for col in reversed(_columns()):
        op.drop_column("orders", col.name)
