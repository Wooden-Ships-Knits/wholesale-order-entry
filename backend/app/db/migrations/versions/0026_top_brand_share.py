"""the half products_per_brand cannot see: how concentrated the shelf is

Revision ID: 0026_top_brand_share
Revises: 0025_top_brands
Create Date: 2026-08-25

`products_per_brand` is a MEAN, and a mean is diluted by exactly the thing that
disguises a house brand. Phoebe Jon carries 114 of its own 124 products plus
nine "brands" holding one glove, one belt and one scarf apiece: 92% of the
shelf under one name, at a mean of 12.4 -- an ordinary boutique's number. It
scored `strong` at HIGH confidence and sat at the top of a rep's call list,
its own $148-$228 sweaters reading as a perfect price match precisely because
they compete with ours.

This is the same error already fixed once on price, where a median hid the
distribution. There a median hid where the knitwear actually sat; here a mean
hides how concentrated the shelf is.

Numeric(5, 4) to match knit_in_band_share, the other measurement persisted so
that a gate can be audited from the table rather than by re-deriving 5.8 GB of
page cache. NULL means no product on the shelf named a brand at all, which is
a different fact from one brand holding everything -- do not read it as zero.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_top_brand_share"
down_revision: Union[str, None] = "0025_top_brands"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "top_brand_share" not in columns:
        op.add_column("prospects", sa.Column("top_brand_share", sa.Numeric(5, 4)))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "top_brand_share" in columns:
        op.drop_column("prospects", "top_brand_share")
