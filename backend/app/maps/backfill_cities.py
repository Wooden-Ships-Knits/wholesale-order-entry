"""Fill `city` on prospects that have a coordinate but no place name.

431 of 1,437 rows draw on the map and read "—" in the rep table's Where
column. OSM located them without an `addr:city` tag, and their `address` is a
street line with no town in it ("7601 Windrose Avenue", "80 West 40th Street"),
so there is nothing to parse. The coordinate is the only thing left to ask.

NOT part of the sweep, and deliberately separate from it. A sweep re-fetches
OSM; this asks a different service about rows OSM has already failed to name,
so re-running the sweep would not fix them and running this does not need one.

    docker compose ... exec backend python -m app.maps.backfill_cities --dry-run
    docker compose ... exec backend python -m app.maps.backfill_cities --limit 20
    docker compose ... exec backend python -m app.maps.backfill_cities

Costs one Google Geocoding call per row (~$5 per 1,000). Safe to stop and
re-run: only rows still lacking a city are asked, and it commits in batches.
"""
import argparse
import json
import logging
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.config import settings
from app.db.models import Prospect

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
BATCH = 25

# In preference order. `locality` is the ordinary answer; Google files some
# places under `postal_town` instead, and an unincorporated place may only have
# a sublocality or a neighbourhood.
#
# administrative_area_level_2 is DELIBERATELY ABSENT: it is a county. Writing
# "San Diego County" into a column a rep reads as a town is worse than leaving
# it empty, because a wrong answer is not retried and an empty one is.
CITY_TYPES = ("locality", "postal_town", "sublocality_level_1", "sublocality",
              "neighborhood")


class LookupRefused(Exception):
    """Google refused the request itself — a key, quota or billing problem.

    Separate from "this coordinate has no town" because the answers are
    opposite: one is a fact about the shop and the run should continue, the
    other is a fact about our configuration and every remaining row will fail
    the same way. Reporting "filled 0, still unnamed 431" for the second is the
    silent failure this class exists to prevent.
    """


# Statuses that mean the request never ran, as opposed to running and finding
# nothing. ZERO_RESULTS is a real answer and is NOT here.
FATAL = ("REQUEST_DENIED", "OVER_QUERY_LIMIT", "OVER_DAILY_LIMIT", "INVALID_REQUEST")


def check_status(payload) -> None:
    """Raise if the response says the request was refused rather than answered."""
    status = payload.get("status")
    if status in FATAL:
        raise LookupRefused(
            f"{status}: {payload.get('error_message') or 'no detail given'}")


def city_from(payload) -> str | None:
    """The town name in a Geocoding response, or None if it names none.

    None rather than "": None reads as "still unanswered" and a later run asks
    again, where an empty string looks like a lookup that succeeded and found
    nothing.
    """
    for result in (payload.get("results") or []):
        components = result.get("address_components") or []
        for want in CITY_TYPES:
            for component in components:
                if want in (component.get("types") or []):
                    name = (component.get("long_name") or "").strip()
                    if name:
                        return name
    return None


def needs_city(row) -> bool:
    """Whether this row can and should be asked about.

    A row that already has a city is never touched: the sweep's `addr:city` is
    the shop's own tag and outranks anything derived from a coordinate. That is
    also what makes this safe to re-run.
    """
    return (not (row.city or "").strip()
            and row.latitude is not None and row.longitude is not None)


def pending_rows(rows) -> list:
    return [r for r in rows if needs_city(r)]


def pending(db) -> list:
    return pending_rows(
        db.execute(select(Prospect).order_by(Prospect.store_name)).scalars().all())


def _lookup(lat, lng) -> dict:
    params = {"latlng": f"{lat},{lng}", "result_type": "|".join(CITY_TYPES),
              "key": settings.google_maps_server_api_key}
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=25) as fh:
        return json.load(fh)


def run(db, limit=None, dry_run=False, lookup=_lookup) -> int:
    rows = pending(db)
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} row(s) have a coordinate and no city", flush=True)
    if dry_run:
        for r in rows[:20]:
            print(f"  would ask  {r.store_name[:38]:38} {r.latitude},{r.longitude}")
        return 0

    filled = missed = 0
    for i, r in enumerate(rows, 1):
        try:
            payload = lookup(r.latitude, r.longitude)
            check_status(payload)       # a refusal stops the run, see below
            city = city_from(payload)
        except LookupRefused as exc:
            # Every remaining row would fail identically, so stopping here is
            # the honest answer -- and it costs nothing further.
            db.commit()
            print(f"\nSTOPPED after {i - 1} row(s): {exc}", flush=True)
            print("Nothing is wrong with the data; the request was refused.",
                  flush=True)
            return filled
        except Exception:
            # One bad lookup must not throw away the rows already paid for.
            logger.exception("lookup failed for %s", r.store_name)
            missed += 1
            continue
        if not city:
            missed += 1
            continue
        r.city = city
        filled += 1
        if i % BATCH == 0:
            db.commit()
            print(f"  {i}/{len(rows)}  filled {filled}", flush=True)
    db.commit()
    print(f"filled {filled}, still unnamed {missed}", flush=True)
    return filled


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="only the first N rows")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be asked, spend nothing")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    if not args.dry_run and not settings.google_maps_server_api_key:
        raise SystemExit("GOOGLE_MAPS_SERVER_API_KEY is not set; nothing to ask.")

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        run(db, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
