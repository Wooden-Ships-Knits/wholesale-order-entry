"""fix the verdict constraint, and record what the assessment actually returns

Revision ID: 0023_prospect_assessment
Revises: 0022_draft_saved_at
Create Date: 2026-08-22

0020 shipped `ck_prospects_verdict` as a copy of the status constraint one line
above it -- `verdict IN ('prospect', 'existing')`. The assessment returns
`strong`, `possible`, `weak` or `insufficient_data`, so every one of those is
rejected. Nothing has noticed because a CHECK passes on NULL and nothing writes
the column yet: the first row ever assessed would have been the first failure.

The three new columns are all things the assessment already returns and had
nowhere to go.

  problems           what judge.check() found wrong with the answer -- an
                     invented brand, or a verdict that breaks a hard rule. It is
                     the only field that says "do not trust this row", so
                     dropping it put unchecked answers in front of a rep with
                     nothing to mark them.
  knit_evidence      where the knitwear was found: the shop's own tags, its
                     products, both, or nowhere. `none` is what forces `weak`
                     under rule 2, so without this column the commonest reason
                     for a weak verdict is unauditable.
  knit_tags_carried  the shop's own tags that name knitwear. Distinct from
                     signature_tags_carried, which asks whether it is
                     merchandised like our customers -- only three of those 78
                     tags name knitwear at all.

`price_range` changes type because the column and the pipeline disagreed about
what it holds. The comment in 0020 promised free text ("$48-$220"); the scraper
produces the spread between cheapest and dearest as a single number, and the
range it was described as cannot be derived -- the payload carries no min or
max. Text would have accepted "463" silently and a rep would have read it as a
price. Numeric(10, 2) matches price_median beside it and sorts.

WHY EVERY STEP BELOW IS CONDITIONAL. 0020 was written on 2026-08-18 and applied;
on 2026-08-21 commit 205741a added its whole assessment block -- 15 columns, an
index and the verdict constraint -- to the same file. Alembic had already
stamped 0020, so on any database that ran the first version those additions
never happened, while a database created afterwards has them. Both exist right
now: the dev database has 33 columns and no `verdict` at all. So this migration
cannot assume either shape. It inspects and adds what is missing, which lands
both on the same schema and is safe to run twice.

The two enumerations are deliberately spelled out here rather than left open.
They are the same bargain the status constraint made and the same one the
verdict constraint got wrong: a typo becomes a category no query counts, and
these values cross a repo boundary (scrapping-bot's analysis/judge.py VERDICTS
and analysis/llm_payload.py _knit_evidence), where nothing else would catch a
rename. If either list changes there, it changes here -- loudly, at the first
write, which is the point.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_prospect_assessment"
down_revision: Union[str, None] = "0022_draft_saved_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# analysis/judge.py::VERDICTS, in the scrapebot.
VERDICTS = ("strong", "possible", "weak", "insufficient_data")
# analysis/llm_payload.py::_knit_evidence, ditto. "products_only" is not a
# weaker answer than "tags+products": of 271 accounts, 97 show knitwear in
# their products alone and none in tags alone.
KNIT_EVIDENCE = ("tags+products", "products_only", "tags_only", "none")


# The block commit 205741a added to 0020 after it had already run. price_range
# is Numeric here, not the Text 0020 declared -- see above; a database that
# never got the column should not be given the wrong type first and altered a
# few lines later.
ASSESSMENT = (
    ("verdict", sa.Text()),
    ("confidence", sa.Text()),
    ("for_the_rep", sa.Text()),
    ("reasons", sa.Text()),
    ("against", sa.Text()),
    ("store_type", sa.Text()),
    ("brand_count", sa.Integer()),
    ("products_per_brand", sa.Numeric(8, 2)),
    ("tag_lift", sa.Numeric(8, 3)),
    ("price_median", sa.Numeric(10, 2)),
    ("price_range", sa.Numeric(10, 2)),
    ("knitwear_share", sa.Numeric(5, 4)),
    ("knitwear_price_median", sa.Numeric(10, 2)),
    ("signature_tags_carried", sa.Text()),
    ("assessed_at", sa.DateTime(timezone=True)),
)

NEW_COLUMNS = (
    ("problems", sa.Text()),
    ("knit_evidence", sa.Text()),
    ("knit_tags_carried", sa.Text()),
)


def _in(column: str, values: Sequence[str]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


def _columns(bind) -> dict:
    return {c["name"]: c["type"]
            for c in sa.inspect(bind).get_columns("prospects")}


def _checks(bind) -> set:
    return {c["name"]
            for c in sa.inspect(bind).get_check_constraints("prospects")}


def _indexes(bind) -> set:
    return {i["name"] for i in sa.inspect(bind).get_indexes("prospects")}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind)

    # 1. Whatever 0020's later edit never delivered here.
    for name, type_ in ASSESSMENT:
        if name not in columns:
            op.add_column("prospects", sa.Column(name, type_))
    if "ix_prospects_verdict" not in _indexes(bind):
        op.create_index("ix_prospects_verdict", "prospects", ["verdict"])

    # 2. The constraint this migration exists for. Dropped only if 0020 got far
    #    enough to create it; created either way.
    if "ck_prospects_verdict" in _checks(bind):
        op.drop_constraint("ck_prospects_verdict", "prospects", type_="check")
    op.create_check_constraint(
        "ck_prospects_verdict", "prospects", _in("verdict", VERDICTS)
    )

    # 3. What the assessment returns and 0020 never had a column for.
    for name, type_ in NEW_COLUMNS:
        if name not in columns:
            op.add_column("prospects", sa.Column(name, type_))
    if "ck_prospects_knit_evidence" not in _checks(bind):
        op.create_check_constraint("ck_prospects_knit_evidence", "prospects",
                                   _in("knit_evidence", KNIT_EVIDENCE))

    # 4. price_range, only where 0020 already made it Text. No USING that tries
    #    to rescue text: nothing writes the column yet, so there is nothing to
    #    salvage, and a regex turning "$48-$220" into 48220 would put a wrong
    #    number in front of a rep instead of stopping.
    if "TEXT" in str(columns.get("price_range", "")).upper():
        op.alter_column(
            "prospects", "price_range",
            existing_type=sa.Text(),
            type_=sa.Numeric(10, 2),
            postgresql_using="NULLIF(price_range, '')::numeric",
        )


def downgrade() -> None:
    """Reverses this migration, not 0020's history.

    The columns in ASSESSMENT are 0020's, however late they arrived, so they
    stay. The verdict constraint is dropped rather than put back the way it was:
    the old one rejected all four real verdicts, so recreating it on a database
    that has since assessed anything would simply fail, and recreating a bug on
    one that has not is not a service to anybody.
    """
    bind = op.get_bind()
    columns = _columns(bind)

    if "NUMERIC" in str(columns.get("price_range", "")).upper():
        op.alter_column(
            "prospects", "price_range",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Text(),
            postgresql_using="price_range::text",
        )

    if "ck_prospects_knit_evidence" in _checks(bind):
        op.drop_constraint("ck_prospects_knit_evidence", "prospects", type_="check")
    for name, _ in reversed(NEW_COLUMNS):
        if name in columns:
            op.drop_column("prospects", name)

    if "ck_prospects_verdict" in _checks(bind):
        op.drop_constraint("ck_prospects_verdict", "prospects", type_="check")
