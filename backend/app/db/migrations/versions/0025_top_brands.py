"""keep the shelf we judged: the brands a shop actually stocks

Revision ID: 0025_top_brands
Revises: 0024_knit_in_band_share
Create Date: 2026-08-24

`top_brands` was computed by store_payload(), shown to the model, used by the
unreadable-shelf gate, and then dropped. Nothing persisted it, so the one rule
that turns on it could not be checked from the table at all -- answering "which
shops only name themselves?" meant re-deriving 5.8 GB of page cache, and the
cache is the first thing anyone will delete.

Text, joined with "; ", exactly as reasons / problems / signature_tags_carried
are joined by assess.JOINED. Not an array or jsonb: those are a new shape in a
table whose four other list columns are already text, and nothing queries
inside this one -- it is read by a person deciding whether a verdict was fair.

ORDER IS THE POINT and it is preserved. The list arrives sorted by how deeply
each brand is stocked, and `brands_echo_domain` reads the FIRST entry. Hill
House Home reads "HILL HOUSE HOME; WOMENS APPAREL_NAP DRESS; ..." -- 946 of its
967 products under its own name, the rest category strings misfiled into the
vendor field. Sorting this column alphabetically would destroy the evidence.

Capped at 20 by TOP_BRANDS, which is what the model was shown: the row records
what the judgement saw, not more.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_top_brands"
down_revision: Union[str, None] = "0024_knit_in_band_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "top_brands" not in columns:
        op.add_column("prospects", sa.Column("top_brands", sa.Text()))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "top_brands" in columns:
        op.drop_column("prospects", "top_brands")
