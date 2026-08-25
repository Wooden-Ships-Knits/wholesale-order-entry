"""whose name is on the clothes, as distinct from whose name is on the shelf

Revision ID: 0027_own_name_share
Revises: 0026_top_brand_share
Create Date: 2026-08-25

`top_brand_share` counts the single deepest vendor string, so a shop dilutes
its own concentration by spelling itself two ways: artemesiamade.com files 56
products under "ARTEMESIAMADE" and one under "ARTEMESIA". `own_name_share`
sums every entry that echoes the domain and reads 66% where the other read 64%.

`knit_own_name_share` is the one that matters to us. A knitwear wholesaler is
not asking "does this shop stock anybody else's goods" but "does it buy
KNITWEAR from anybody else". Artemesia buys candles, soap and greetings cards
from thirteen brands and its clothes from nobody.

BOTH ARE PERSISTED BECAUSE NEITHER DECIDES ALONE, and the reason is a near
miss worth recording. tinademel.com sits at 62.3% own-name across its
catalogue -- two points from Artemesia's 66% -- and stocks 23 Wooden Ships
products. There is no threshold on that axis that separates a customer from a
label. It is spared because its knit shelf is bought from other people: 48
third-party sweaters against its own. One signal being wrong is not enough to
hide a paying customer, which is the whole design.

NULL in knit_own_name_share means the knit shelf was too short to carry a
proportion at all (below MIN_KNIT_FOR_SHARE). That is a different fact from
"all of it is their own" and must never be read as 1.0.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_own_name_share"
down_revision: Union[str, None] = "0026_top_brand_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("own_name_share", "knit_own_name_share")


def upgrade() -> None:
    bind = op.get_bind()
    have = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    for name in COLUMNS:
        if name not in have:
            op.add_column("prospects", sa.Column(name, sa.Numeric(5, 4)))


def downgrade() -> None:
    bind = op.get_bind()
    have = {c["name"] for c in sa.inspect(bind).get_columns("prospects")}
    for name in COLUMNS:
        if name in have:
            op.drop_column("prospects", name)
