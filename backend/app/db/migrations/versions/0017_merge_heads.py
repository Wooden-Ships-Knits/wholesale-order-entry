"""merge the signature-reminder and split-column migration branches

Revision ID: 0017_merge_heads
Revises: 0016_signature_reminders, 0016_split_columns
Create Date: 2026-08-07

Two branches both added a migration on top of 0015_signature_link:

    0015_signature_link
      ├── 0016_signature_reminders   (chasers for unsigned orders)
      └── 0016_split_columns         (split / split_with as two columns)

Same shape as 0014_merge_heads: the filenames differ so git merged them
cleanly, but Alembic was left with two heads and the container's
`alembic upgrade head` failed with "Multiple head revisions are present" —
which, because the CMD is `alembic upgrade head && uvicorn ...`, stopped the
backend from starting at all.

Safe to rejoin in either order: both add columns to `orders`, and they add
different ones. This revision has no schema of its own.

"""
from typing import Sequence, Union

revision: str = "0017_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0016_signature_reminders",
    "0016_split_columns",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: a merge point carries no schema change of its own."""


def downgrade() -> None:
    """No-op: splitting back into two heads is the reverse, handled by Alembic."""
