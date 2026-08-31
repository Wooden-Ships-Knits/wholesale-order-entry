"""Fill `city` on prospects that have a coordinate but no place name.

431 of 1,437 rows draw on the map and read "—" in the rep table's Where column.
OSM located them without an `addr:city` tag, and their `address` is a street
line with no town in it ("7601 Windrose Avenue", "80 West 40th Street"), so
there is nothing to parse. The coordinate is the only thing left to ask.

ANSWERED BY THE US CENSUS GEOCODER: free, no API key, no quota to exhaust, and
authoritative for the only country this data covers — all 431 rows carry a US
state, across 44 of them. Google's Geocoding API answers the same question and
costs about $5 per 1,000; it is also refused by the key this project currently
holds, which is a browser key with referrer restrictions.

NOT part of the sweep and deliberately separate from it. A sweep re-fetches
OSM; this asks a different service about rows OSM has already failed to name,
so re-running the sweep would not fix them.

    docker compose ... exec backend python -m app.maps.backfill_cities --dry-run
    docker compose ... exec backend python -m app.maps.backfill_cities --limit 20
    docker compose ... exec backend python -m app.maps.backfill_cities

Safe to stop and re-run: only rows still lacking a city are asked, and it
commits in batches.
"""
import argparse
import json
import logging
import time
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.models import Prospect

logger = logging.getLogger(__name__)

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
BATCH = 25
PAUSE = 0.2   # courtesy to a free public service, not a documented limit

# In preference order. An incorporated place is a real city or town with limits;
# a CDP is the Census's name for a populated place that has none — Paradise CDP
# holds the Las Vegas Strip, so refusing to read it would leave a shop there
# looking lost rather than merely unincorporated.
PLACE_LAYERS = ("Incorporated Places", "Census Designated Places")

# Census writes the TYPE after the name, in lower case: "Carmel city",
# "Chapel Hill town", "Paradise CDP". Case matters and is the whole trick --
# "Kansas City city" must become "Kansas City", not "Kansas".
SUFFIXES = (" city", " town", " village", " borough", " municipality",
            " CDP", " zona urbana", " comunidad")


class LookupRefused(Exception):
    """The service refused the request rather than answering it.

    Separate from "this coordinate lies inside no place", because the two
    demand opposite responses: one is a fact about the shop and the run should
    continue, the other is a fact about the service and every remaining row
    will fail identically. Reporting "filled 0, still unnamed 431" for the
    second is the silent failure this class exists to prevent.
    """


def clean_place(name: str) -> str:
    """"Carmel city" -> "Carmel". Case-sensitive, deliberately."""
    for suffix in SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)].strip()
    return name.strip()


def check_status(payload) -> None:
    """Raise if the response says the request was refused rather than answered."""
    errors = payload.get("errors")
    if errors:
        raise LookupRefused("; ".join(str(e) for e in errors))
    if "result" not in payload:
        raise LookupRefused(f"unrecognised response: {list(payload)[:5]}")


def city_from(payload) -> str | None:
    """The town this coordinate sits in, or None if it sits in none.

    None rather than "": None reads as "still unanswered" and a later run asks
    again, where an empty string looks like a lookup that succeeded and found
    nothing. Rural addresses genuinely fall outside every place.
    """
    geographies = (payload.get("result") or {}).get("geographies") or {}
    for layer in PLACE_LAYERS:
        for item in geographies.get(layer) or []:
            name = clean_place((item.get("NAME") or "").strip())
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
    params = {"x": lng, "y": lat, "benchmark": "Public_AR_Current",
              "vintage": "Current_Current", "layers": ",".join(PLACE_LAYERS),
              "format": "json"}
    url = f"{CENSUS_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=25) as fh:
        return json.load(fh)


def run(db, limit=None, dry_run=False, lookup=_lookup, pause=0.0) -> int:
    rows = pending(db)
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} row(s) have a coordinate and no city", flush=True)
    if dry_run:
        for r in rows[:20]:
            print(f"  would ask  {r.store_name[:38]:38} {r.latitude},{r.longitude}")
        return 0

    filled = unplaced = failed = 0
    for i, r in enumerate(rows, 1):
        try:
            payload = lookup(r.latitude, r.longitude)
            check_status(payload)
            city = city_from(payload)
        except LookupRefused as exc:
            db.commit()
            print(f"\nSTOPPED after {i - 1} row(s): {exc}", flush=True)
            print("Nothing is wrong with the data; the request was refused.",
                  flush=True)
            return filled
        except Exception:
            # One bad lookup must not throw away the rows already written.
            logger.exception("lookup failed for %s", r.store_name)
            failed += 1
            continue
        if city:
            r.city = city
            filled += 1
        else:
            unplaced += 1
        if i % BATCH == 0:
            db.commit()
            print(f"  {i}/{len(rows)}  filled {filled}", flush=True)
        if pause:
            time.sleep(pause)
    db.commit()
    print(f"filled {filled}, inside no place {unplaced}, lookup failed {failed}",
          flush=True)
    return filled


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, help="only the first N rows")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be asked, ask nothing")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        run(db, limit=args.limit, dry_run=args.dry_run, pause=PAUSE)


if __name__ == "__main__":
    main()
