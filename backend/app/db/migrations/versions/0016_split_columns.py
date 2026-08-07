"""Split as two columns instead of one display string.

`split_with` held a rendered string — "Y — Denise Arnett", "N", or "" — which
was fine while it only had to print on a PDF. It now has to fill two Salesforce
picklists (Split_Commission__c and Split_With__c), and a display string is the
wrong thing to parse for that.

After this, `split` is the yes/no answer and `split_with` is just the name. The
PDF re-derives the old string for display.

Backfill (23 rows at the time of writing):
    'Y — <name>' -> split=true,  split_with='<name>'
    'Y'          -> split=true,  split_with=NULL     (name was blank)
    'N'          -> split=false, split_with=NULL
    '' / NULL    -> split=NULL,  split_with=NULL     (never answered)

Revision ID: 0016_split_columns
Revises: 0015_signature_link
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_split_columns"
down_revision: Union[str, None] = "0015_signature_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The em dash the old writer used (U+2014), not a hyphen.
_SEP = "—"


def upgrade() -> None:
    op.add_column("orders", sa.Column("split", sa.Boolean(), nullable=True))

    # Order matters: read split_with to set split, THEN rewrite split_with.
    op.execute(
        """
        UPDATE orders SET split = CASE
            WHEN split_with LIKE 'Y%' THEN true
            WHEN split_with = 'N'     THEN false
            ELSE NULL
        END
        """
    )
    # Keep only what follows the em dash; everything else (bare 'Y', 'N', '')
    # carried no name.
    op.execute(
        f"""
        UPDATE orders SET split_with = CASE
            WHEN position('{_SEP}' in split_with) > 0
                THEN NULLIF(btrim(substr(split_with, position('{_SEP}' in split_with) + 1)), '')
            ELSE NULL
        END
        """
    )


def downgrade() -> None:
    # Rebuild the display string, then drop the column.
    op.execute(
        f"""
        UPDATE orders SET split_with = CASE
            WHEN split IS TRUE  AND coalesce(split_with, '') <> ''
                THEN 'Y {_SEP} ' || split_with
            WHEN split IS TRUE  THEN 'Y'
            WHEN split IS FALSE THEN 'N'
            ELSE ''
        END
        """
    )
    op.drop_column("orders", "split")
