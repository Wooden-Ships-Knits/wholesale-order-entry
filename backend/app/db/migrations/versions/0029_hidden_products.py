"""taking a style+color off the order form without touching Salesforce

Revision ID: 0029_hidden_products
Revises: 0028_tax_cert_cleared
Create Date: 2026-09-05

A price book carries every style+color the season was built with, including
the ones that sold out, never got made, or were pulled after the line sheet
went out. The order form shows all of them because it shows the price book,
and the only lever anyone had was to edit the price book in Salesforce --
which changes what the whole company sees, for the sake of one web form.

OUR DATA, NOT THEIRS. Salesforce owns the catalogue; this table owns one
opinion about it, keyed on (season, style, color) -- the grain
mapping.group_products() already returns. Nothing is written back to
Salesforce, and dropping this table only makes hidden styles visible again.

THE KEY IS THE WHOLE ROW. Hiding is an INSERT, unhiding is a DELETE, and the
primary key makes both idempotent -- two admins clicking the same checkbox
cannot produce two rows or a stuck one. A `hidden boolean` column instead
would need every reader to remember that a missing row and a false row mean
the same thing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_hidden_products"
down_revision: Union[str, None] = "0028_tax_cert_cleared"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "hidden_products"


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("season_code", sa.Text(), primary_key=True),
        sa.Column("style_name", sa.Text(), primary_key=True),
        sa.Column("color", sa.Text(), primary_key=True),
        sa.Column(
            "hidden_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE in sa.inspect(bind).get_table_names():
        op.drop_table(TABLE)
