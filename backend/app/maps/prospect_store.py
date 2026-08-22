"""Persist a sweep's output into `prospects`.

app/maps/prospecting.py finds shops and returns a DataFrame. This puts them in
the database, keyed on `osm_id`, so a re-run UPDATES a shop rather than
duplicating it -- which is also what stops a rep's shortlist losing its target.

THE ONE RULE HERE: the sweep owns SWEEP_COLUMNS and nothing else. Every other
column on the row -- the whole assessment block, and the marks in
prospect_marks -- belongs to something that costs money or belongs to a person,
and a sweep is re-run every time a filter is retuned. `DO UPDATE SET` therefore
names its columns one by one. An `EXCLUDED.*`-style blanket update would erase
a verdict, its reasons and its assessed_at on every sweep, and the next
assessment run would cheerfully pay for all of them again.

    from app.maps import prospect_store as ps
    ps.upsert(db, ps.rows_from_csv("prospek-rande.csv"), territory="FL - Jason Hilsenrad")
"""
import csv
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Prospect

logger = logging.getLogger(__name__)

# sweep column -> prospects column. Named rather than derived: `found_near` and
# `vicinity` are the Places vocabulary discover_osm kept for compatibility, and
# guessing at them by name would silently drop a shop's town and street.
FIELDS = {
    "osm_id": "osm_id", "place_id": "place_id", "store_name": "store_name",
    "latitude": "latitude", "longitude": "longitude",
    "found_near": "city", "vicinity": "address", "postcode": "postcode",
    # `state` is how a territory that straddles a border is filtered, and the
    # rep page prints it. Free from the sweep -- discover_osm queries one state
    # at a time -- but only if it is named here: the first 225 rows were loaded
    # without it and the column sat NULL with nothing to show it had been lost.
    "state": "state",
    "types": "types", "clothes": "clothes", "womenswear": "womenswear",
    "second_hand": "second_hand", "opening_hours": "opening_hours",
    "website": "website", "phone": "phone", "email": "email",
    "instagram": "instagram", "rating": "rating", "review_count": "review_count",
    "nearest_stockist": "nearest_stockist", "distance_miles": "distance_miles",
    "potential_conflict": "potential_conflict", "drive_minutes": "drive_minutes",
}

BOOLEANS = ("womenswear", "potential_conflict")
INTEGERS = ("review_count", "drive_minutes")
NUMBERS = ("latitude", "longitude", "rating", "distance_miles")

# What a sweep is allowed to overwrite on a shop it has seen before.
# `first_seen_at` is absent on purpose: it records when we first found the shop,
# and a re-run has not re-found it for the first time.
SWEEP_COLUMNS = tuple(FIELDS.values()) + ("territory", "last_seen_at")


def _clean(value):
    """'' and whitespace become NULL. A blank cell is an absent fact, not a value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value):
    text = _clean(value)
    if text is None:
        return None
    return text.lower() in ("true", "1", "yes", "t")


def sweep_values(row: dict, territory=None) -> dict:
    """One sweep row as prospects column values, or None if it names no element.

    Deliberately returns ONLY sweep-owned columns. Nothing here can name an
    assessment column, so no caller can accidentally clear one.
    """
    osm_id = _clean(row.get("osm_id"))
    if not osm_id:
        return None

    out = {}
    for src, dest in FIELDS.items():
        value = _clean(row.get(src))
        if dest in BOOLEANS:
            out[dest] = _bool(row.get(src))
        elif value is None:
            out[dest] = None
        elif dest in INTEGERS:
            out[dest] = int(float(value))
        elif dest in NUMBERS:
            out[dest] = float(value)
        else:
            out[dest] = value

    # A shop with no name is still a real element; "" would read as one called
    # nothing, and store_name is NOT NULL.
    out["store_name"] = out.get("store_name") or osm_id
    if territory:
        out["territory"] = territory
    return out


def rows_from_csv(path) -> list:
    """A sweep CSV as rows. csv.DictReader, so a column order change is harmless."""
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh)]


def upsert(db, rows, territory=None) -> dict:
    """Write these shops, updating any we have seen before. Returns a summary.

    One statement per row rather than one for all of them: at a few thousand
    shops the difference is not worth the loss of being able to say which row
    failed, and a sweep is run by hand.
    """
    now = datetime.now(timezone.utc)
    seen = skipped = 0
    before = db.execute(select(func.count()).select_from(Prospect)).scalar_one()

    for row in rows:
        values = sweep_values(row, territory)
        if values is None:
            skipped += 1
            continue
        values["last_seen_at"] = now

        stmt = insert(Prospect).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["osm_id"],
            # Named one by one. See the module docstring: this list is the only
            # thing standing between a re-sweep and every verdict we paid for.
            set_={c: stmt.excluded[c] for c in SWEEP_COLUMNS if c in values},
        )
        db.execute(stmt)
        seen += 1

    db.commit()
    after = db.execute(select(func.count()).select_from(Prospect)).scalar_one()
    summary = {"rows": seen, "skipped": skipped,
               "inserted": after - before, "updated": seen - (after - before),
               "total": after}
    logger.info("Sweep upsert: %s", summary)
    return summary
