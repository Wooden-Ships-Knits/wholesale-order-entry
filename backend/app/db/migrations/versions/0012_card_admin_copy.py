"""card expiry + encrypted admin-copy PDF (transient full card number)

Revision ID: 0012_card_admin_copy
Revises: 0011_rank
Create Date: 2026-07-28

The monitoring team keys the card into Salesforce by hand (Kugamon encrypts it
in its own Visualforce page, so there is no API to write it to). They need the
number after submit, but it must not sit in a mailbox or on disk.

card_pdf_enc holds the admin-copy PDF — the only artefact showing the full
number — AES-256-GCM encrypted with a key held outside the database. It is
purged on Accept/Decline and by the retention sweep. The customer copy is
rendered separately with the number masked to the last 4.

Still no CVV column, and no card-number column: rule 1 stands.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_card_admin_copy"
down_revision: Union[str, None] = "0011_rank"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expiry is cardholder data, not sensitive authentication data — clear text.
    op.add_column("orders", sa.Column("card_exp", sa.Text()))
    op.add_column("orders", sa.Column("card_pdf_enc", sa.LargeBinary()))


def downgrade() -> None:
    op.drop_column("orders", "card_pdf_enc")
    op.drop_column("orders", "card_exp")
