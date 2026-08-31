"""closing a tax-cert chase that a different order already answered

Revision ID: 0028_tax_cert_cleared
Revises: 0027_own_name_share
Create Date: 2026-08-28

A rep writing a batch for one new store produces one order per ship window --
four rows for PAM'S PEARL in a single morning -- and each one opens its own
"no certificate" chase. The buyer sends the document once. Without somewhere to
record that, the only ways to stop the other three from looking outstanding
were to mail the same buyer four times or to leave the column permanently
yellow, and a column that is always yellow stops being read at all.

TWO COLUMNS, NOT A RESOLUTION ENUM. The conflict fields next door carry
`cleared | real_conflict` because the rep can answer in a way that stops the
order. Nothing the buyer says about a tax certificate does that -- the document
either arrives or the sale is taxable -- so the only state worth recording is
"a person decided this row needs no further chasing", plus their reason.

THIS IS NOT A CERTIFICATE. `hasCertificate` still reads the uploaded file and
still answers "is there a document against this order"; clearing does not
forge one, and the Open link does not appear. The distinction matters at audit
time, which is the one time anybody will care: a cleared row must still be
traceable to the order that holds the actual document, which is what the note
is for.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_tax_cert_cleared"
down_revision: Union[str, None] = "0027_own_name_share"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = {
    "tax_cert_cleared_at": sa.DateTime(timezone=True),
    "tax_cert_cleared_note": sa.Text(),
}


def upgrade() -> None:
    bind = op.get_bind()
    have = {c["name"] for c in sa.inspect(bind).get_columns("orders")}
    for name, type_ in COLUMNS.items():
        if name not in have:
            op.add_column("orders", sa.Column(name, type_))


def downgrade() -> None:
    bind = op.get_bind()
    have = {c["name"] for c in sa.inspect(bind).get_columns("orders")}
    for name in COLUMNS:
        if name in have:
            op.drop_column("orders", name)
