"""merge the card-copy and conflict-reply migration branches

Revision ID: 0014_merge_heads
Revises: 0012_card_admin_copy, 0013_conflict_ai_suggestion
Create Date: 2026-07-29

Two feature branches both added a migration on top of 0010_email_sent_at:

    0010_email_sent_at
      ├── 0011_rank -> 0012_card_admin_copy                    (card admin copy)
      └── 0011_conflict_resolution -> 0012_inbound_replies
              -> 0013_conflict_ai_suggestion                   (conflict replies)

Git merged the files cleanly because the filenames differ, but Alembic was left
with two heads and `upgrade head` became ambiguous — the backend failed at
startup with "Multiple head revisions are present". This revision has no schema
of its own; it just rejoins the two branches into a single head.

"""
from typing import Sequence, Union

revision: str = "0014_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0012_card_admin_copy",
    "0013_conflict_ai_suggestion",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: a merge point carries no schema change of its own."""


def downgrade() -> None:
    """No-op: splitting back into two heads is the reverse, handled by Alembic."""
