"""record what share of a shop's knitwear is priced where our product sits

Revision ID: 0024_knit_in_band_share
Revises: 0023_prospect_assessment
Create Date: 2026-08-24

Rule 3 used to be decided on `knitwear_price_median` alone, and a median is not
a floor: half a shop's knitwear is cheaper than it by definition. Measured on
the 1,381 scored rows, that cost us real customers. Sandy's Boutique -- 45
brands at 7.1 products each, against an account median of 9.2 -- was answered
`weak` because its knitwear median is $218, $18 over our band. A third of its
knitwear is priced inside that band and its p25 is $125.

Meanwhile Ypsilon Dresses sits at $250, only 8% higher, and carries NOTHING in
our band. One number cannot tell those two apart. This one can, so it is stored
beside the median rather than derived at read time: a rep is shown the verdict,
and the column that decided it has to be there to check.

Numeric(5, 4) matches `knitwear_share` above it -- a share, four decimals, and
it sorts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_knit_in_band_share"
down_revision: Union[str, None] = "0023_prospect_assessment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Conditional for the same reason 0023 is: this repo has already shipped a
    # migration that was edited after it ran, so two database shapes exist.
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "knit_in_band_share" not in columns:
        op.add_column("prospects",
                      sa.Column("knit_in_band_share", sa.Numeric(5, 4)))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    if "knit_in_band_share" in columns:
        op.drop_column("prospects", "knit_in_band_share")
