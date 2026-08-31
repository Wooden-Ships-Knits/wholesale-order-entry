"""Filling postcode and street from the coordinate, for rows OSM never tagged.

302 of 1,437 prospects have no `address`: the sweep already reads OSM's
addr:housenumber and addr:street, so a blank one means OSM itself has none.
300 of those 302 have no postcode either.

Measured on 20 of them before this was written: a postcode comes back every
time, a real street address only 3 times in 20. The other 17 return the
NEAREST ROAD, and the shops are Reformation, Marciano, Nine West Outlet —
chains inside malls, whose nearest road is the mall's ring road. "Ring Road
West" in an address column reads as an address and is not one.

The network is injected, so nothing here opens a socket.
"""
from types import SimpleNamespace

import pytest

from app.maps import backfill_addresses as ba


def _reply(**address):
    return {"address": address}


# --- the street ------------------------------------------------------------

def test_a_house_number_and_a_road_are_a_real_address():
    assert ba.street_from(_reply(house_number="7606", road="5th Avenue")) == "7606 5th Avenue"


def test_a_road_with_no_number_is_refused():
    """THE CASE THIS EXISTS FOR. A shop inside a mall sits nearest the mall's
    ring road, so Nominatim answers "Ring Road West" — the road it is near,
    not the address it has. Writing that is worse than leaving it blank: a
    wrong answer is never retried and a blank one is."""
    assert ba.street_from(_reply(road="Ring Road West")) is None


def test_no_road_at_all_is_none():
    assert ba.street_from(_reply(postcode="89109")) is None


# --- the postcode ----------------------------------------------------------

def test_the_postcode_is_taken_when_offered():
    assert ba.postcode_from(_reply(postcode="75231")) == "75231"


def test_a_missing_postcode_is_none_not_an_empty_string():
    """None reads as "still unanswered" and a later run retries it."""
    assert ba.postcode_from(_reply(road="Main Street")) is None


# --- which rows may be asked about -----------------------------------------

def _row(address="", postcode="", lat=1.0, lng=2.0):
    return SimpleNamespace(store_name="Shop", address=address, postcode=postcode,
                           latitude=lat, longitude=lng)


def test_a_row_missing_either_field_is_worth_asking_about():
    assert ba.pending_rows([_row(address="1 High Street", postcode="")]) != []
    assert ba.pending_rows([_row(address="", postcode="12345")]) != []


def test_a_row_with_both_is_left_alone():
    assert ba.pending_rows([_row(address="1 High Street", postcode="12345")]) == []


def test_a_row_with_no_coordinates_cannot_be_asked():
    assert ba.pending_rows([_row(lat=None, lng=None)]) == []


# --- an existing value is never overwritten --------------------------------

def test_an_address_the_sweep_already_found_is_not_replaced(monkeypatch):
    """OSM's own addr:street is the shop's tag and outranks anything derived
    from a coordinate — and a backfill that overwrites cannot be re-run."""
    row = _row(address="1 High Street", postcode="")
    monkeypatch.setattr(ba, "pending", lambda db: [row])
    ba.run(SimpleNamespace(commit=lambda: None),
           lookup=lambda lat, lng: _reply(house_number="99", road="Wrong Road",
                                          postcode="12345"))
    assert row.address == "1 High Street"
    assert row.postcode == "12345", "the missing half is still filled"


# --- a refusal is not an answer --------------------------------------------

def test_being_rate_limited_stops_the_run(monkeypatch):
    """Nominatim is a free service on a one-request-a-second courtesy limit.
    Being turned away is a fact about us, not about the shops, and every
    remaining row would be turned away identically."""
    asked = []

    def refuse(lat, lng):
        asked.append(1)
        raise ba.LookupRefused("429 Too Many Requests")

    rows = [_row() for _ in range(5)]
    monkeypatch.setattr(ba, "pending", lambda db: rows)
    ba.run(SimpleNamespace(commit=lambda: None), lookup=refuse)
    assert len(asked) == 1, "it must not ask for the other four"


def test_a_coordinate_nominatim_cannot_place_is_an_answer_not_a_refusal():
    """Nominatim says {"error": "Unable to geocode"} for a point in open water.
    That is a fact about the point and must not halt the other rows."""
    assert ba.street_from({"error": "Unable to geocode"}) is None
    assert ba.postcode_from({"error": "Unable to geocode"}) is None
