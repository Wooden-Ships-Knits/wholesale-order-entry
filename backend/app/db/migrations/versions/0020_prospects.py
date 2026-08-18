"""prospect sweep results, and each rep's shortlist

Revision ID: 0020_prospects
Revises: 0019_rep_followup
Create Date: 2026-08-15

Moves the output of app/maps/prospecting.py out of CSVs and into the database
so /reps can read it.

Keyed on osm_id rather than the row id: the sweep is re-run whenever the
filters change, and matching on the OSM element lets a re-run update a shop in
place instead of duplicating it.

Marks live in their own table on purpose. The sweep rewrites prospect rows
wholesale, so a flag stored on `prospects` would be erased every time the
filters were retuned — and a shortlist belongs to one rep, while a column could
only hold one opinion.

`enriched_at` is not decoration. The OSM half of a row is open data and may be
kept indefinitely; the Google half (website, phone, rating, reviews) is Places
content that Google's terms only permit caching for a limited period. Recording
when it was fetched is what makes refreshing or blanking it possible later.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_prospects"
down_revision: Union[str, None] = "0019_rep_followup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prospects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # identity
        sa.Column("osm_id", sa.Text(), nullable=False),
        sa.Column("place_id", sa.Text()),
        sa.Column("store_name", sa.Text(), nullable=False),
        # 'prospect' | 'existing'. Set by classify_existing: an OSM shop that
        # matched a Salesforce account is kept and labelled rather than dropped,
        # so a re-sweep need not re-decide and a human can audit the matcher.
        # NOT a mirror of Salesforce — 47 of 102 Florida accounts have no OSM
        # record at all, so `existing` here means "matched in OSM", never "all
        # our stockists". The map still reads accounts live from Salesforce.
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'prospect'")
        ),
        sa.Column("matched_account", sa.Text()),  # the Salesforce Name it matched
        sa.Column("matched_by", sa.Text()),  # phone | domain | name+distance
        # where
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("city", sa.Text()),
        sa.Column("address", sa.Text()),
        sa.Column("state", sa.Text()),
        sa.Column("postcode", sa.Text()),
        sa.Column("territory", sa.Text()),
        # qualifying signals (OSM tags, free)
        sa.Column("clothes", sa.Text()),
        sa.Column("womenswear", sa.Boolean()),
        sa.Column("second_hand", sa.Text()),
        sa.Column("brand", sa.Text()),
        sa.Column("types", sa.Text()),
        sa.Column("opening_hours", sa.Text()),
        # contact
        sa.Column("website", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("instagram", sa.Text()),
        # Google-only
        sa.Column("rating", sa.Numeric(2, 1)),
        sa.Column("review_count", sa.Integer()),
        sa.Column("review_text", sa.Text()),
        sa.Column("enriched_at", sa.DateTime(timezone=True)),
        # conflict
        sa.Column("potential_conflict", sa.Boolean()),
        sa.Column("nearest_stockist", sa.Text()),
        sa.Column("distance_miles", sa.Numeric(6, 1)),
        sa.Column("drive_minutes", sa.Integer()),
        # provenance
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    # Unique, not just indexed: the upsert the sweep performs depends on it.
    op.create_index("ix_prospects_osm_id", "prospects", ["osm_id"], unique=True)
    op.create_index("ix_prospects_territory", "prospects", ["territory"])
    op.create_index("ix_prospects_status", "prospects", ["status"])
    # A typo would otherwise create a third, silent status that no query counts.
    op.create_check_constraint(
        "ck_prospects_status", "prospects", "status IN ('prospect', 'existing')"
    )

    op.create_table(
        "prospect_marks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "prospect_id",
            sa.Uuid(),
            sa.ForeignKey("prospects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rep_name", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        # Un-starring deletes the row, so at most one per (rep, prospect).
        sa.UniqueConstraint("prospect_id", "rep_name", name="uq_prospect_mark"),
    )
    op.create_index("ix_prospect_marks_prospect_id", "prospect_marks", ["prospect_id"])
    op.create_index("ix_prospect_marks_rep_name", "prospect_marks", ["rep_name"])


def downgrade() -> None:
    op.drop_table("prospect_marks")
    op.drop_table("prospects")
