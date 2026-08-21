"""buyers can save a draft through the signing link

Revision ID: 0022_draft_saved_at
Revises: 0021_rep_followup_stages
Create Date: 2026-08-19

The signing link used to be all-or-nothing: review the order and sign, or lose
your edits. Buyers now get a Save draft button, so a large order can be built
up over several sittings and the link picks up where they left off.

One nullable timestamp is all the state that needs storing. The edits
themselves go into the order's own columns and lines — a draft IS the order,
just not yet signed. What was missing was any way to tell "this is what the rep
wrote" from "this is what the buyer has been changing", which is what /admin
needs before accepting a total that may still move.

Deliberately NOT touched by signing: the timestamp records the last draft save
and stays put, so the sequence of events remains readable afterwards.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_draft_saved_at"
down_revision: Union[str, None] = "0021_rep_followup_stages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("draft_saved_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("orders", "draft_saved_at")
