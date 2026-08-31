"""Fill `postcode` and `address` from the coordinate, for rows OSM never tagged.

302 of 1,437 prospects have no `address`. The sweep already reads OSM's
`addr:housenumber` and `addr:street` (prospecting.discover_osm) and maps them
through `vicinity`, so a blank one means OSM itself carries no address for that
element. Re-running the sweep cannot fix it; a different service has to be
asked. 300 of those 302 have no postcode either.

ANSWERED BY NOMINATIM, OSM's own geocoder: free, no API key. It derives an
address from the nearest addressable feature rather than from the shop's tags,
which is exactly why it can answer where the tags are silent -- and exactly why
its answer needs reading carefully.

WHAT IT WILL AND WILL NOT WRITE. Measured on 20 of the 302 before this was
written:

    postcode                      20 of 20
    house number AND street        3 of 20
    nearest road, no number       17 of 20

Those 17 are shops inside malls -- Reformation, Marciano, Nine West Outlet --
whose nearest road is the mall's ring road: "Ring Road West", "Fashion Show
Drive". A bare road name in an address column READS AS AN ADDRESS AND IS NOT
ONE, so it is refused. A wrong answer is never retried; a blank one is.

    docker compose ... exec backend python -m app.maps.backfill_addresses --dry-run
    docker compose ... exec backend python -m app.maps.backfill_addresses --limit 20
    docker compose ... exec backend python -m app.maps.backfill_addresses

Safe to stop and re-run: an existing value is never overwritten, so only the
still-missing half of a row is asked about.
"""
import argparse
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import select

from app.db.models import Prospect

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
# Nominatim's usage policy asks for an identifying User-Agent and at most one
# request a second. Both are conditions of using it at all, not optimisations.
USER_AGENT = "wooden-ships-wholesale-prospecting/1.0 (wholesale@wooden-ships.com)"
PAUSE = 1.1
BATCH = 25

# HTTP codes that mean we were turned away rather than answered.
REFUSAL_CODES = (403, 429, 503)


class LookupRefused(Exception):
    """The service turned the request away rather than answering it.

    Separate from "this coordinate has no street", because the two demand
    opposite responses: one is a fact about the shop and the run continues, the
    other is a fact about us and every remaining row will fail identically.
    """


def _address(payload) -> dict:
    return payload.get("address") or {}


def street_from(payload) -> str | None:
    """A real street address, or None.

    A house number is REQUIRED. Without one Nominatim is naming the road it
    found nearest, which for a shop inside a mall is the mall's ring road --
    true about the geometry, false as an address, and indistinguishable from a
    real one once it is written into the column.
    """
    a = _address(payload)
    number, road = (a.get("house_number") or "").strip(), (a.get("road") or "").strip()
    if not number or not road:
        return None
    return f"{number} {road}"


def postcode_from(payload) -> str | None:
    """The postcode, or None. No interpretation needed: it is a fact about the
    point rather than a guess about the building."""
    return (_address(payload).get("postcode") or "").strip() or None


def needs_lookup(row) -> bool:
    """Whether this row has a coordinate and is still missing either field."""
    if row.latitude is None or row.longitude is None:
        return False
    return not (row.address or "").strip() or not (row.postcode or "").strip()


def pending_rows(rows) -> list:
    return [r for r in rows if needs_lookup(r)]


def pending(db) -> list:
    return pending_rows(
        db.execute(select(Prospect).order_by(Prospect.store_name)).scalars().all())


def _lookup(lat, lng) -> dict:
    params = {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": "18",
              "addressdetails": "1"}
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=25) as fh:
            return json.load(fh)
    except urllib.error.HTTPError as exc:
        if exc.code in REFUSAL_CODES:
            raise LookupRefused(f"HTTP {exc.code} {exc.reason}") from exc
        raise


def run(db, limit=None, dry_run=False, lookup=_lookup, pause=0.0) -> int:
    rows = pending(db)
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} row(s) have a coordinate and are missing a postcode "
          f"or a street", flush=True)
    if dry_run:
        for r in rows[:20]:
            missing = ", ".join(
                m for m, v in (("street", r.address), ("postcode", r.postcode))
                if not (v or "").strip())
            print(f"  would ask  {r.store_name[:34]:34} for {missing}")
        return 0

    streets = postcodes = no_street = failed = 0
    for i, r in enumerate(rows, 1):
        try:
            payload = lookup(r.latitude, r.longitude)
        except LookupRefused as exc:
            db.commit()
            print(f"\nSTOPPED after {i - 1} row(s): {exc}", flush=True)
            print("Nothing is wrong with the data; the request was turned away.",
                  flush=True)
            return streets + postcodes
        except Exception:
            # One bad lookup must not throw away the rows already written.
            logger.exception("lookup failed for %s", r.store_name)
            failed += 1
            continue

        if not (r.address or "").strip():
            street = street_from(payload)
            if street:
                r.address = street
                streets += 1
            else:
                no_street += 1
        if not (r.postcode or "").strip():
            postcode = postcode_from(payload)
            if postcode:
                r.postcode = postcode
                postcodes += 1

        if i % BATCH == 0:
            db.commit()
            print(f"  {i}/{len(rows)}  streets {streets}, postcodes {postcodes}",
                  flush=True)
        if pause:
            time.sleep(pause)

    db.commit()
    print(f"streets {streets}, postcodes {postcodes}, "
          f"no street to give {no_street}, lookup failed {failed}", flush=True)
    return streets + postcodes


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
