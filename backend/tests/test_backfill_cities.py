"""Filling the city on rows that have coordinates but no place name.

431 of 1,437 prospects draw on the map and read "—" in the Where column: OSM
located them without an addr:city tag, and their `address` is a street line
with no town in it ("7601 Windrose Avenue"). The coordinate is all that is left.

Answered by the US Census geocoder — free, no API key, and authoritative for
the only country this data covers (44 states, 0 rows without one).

The network is injected, so nothing here opens a socket.
"""
from types import SimpleNamespace

import pytest

from app.maps import backfill_cities as bc


def _places(incorporated=(), designated=()):
    """A Census `geographies/coordinates` response."""
    return {"result": {"geographies": {
        "Incorporated Places": [{"NAME": n} for n in incorporated],
        "Census Designated Places": [{"NAME": n} for n in designated],
    }}}


# --- reading the answer ----------------------------------------------------

def test_an_incorporated_place_is_the_city():
    assert bc.city_from(_places(incorporated=["Carmel city"])) == "Carmel"


def test_an_unincorporated_place_still_answers():
    """Paradise CDP holds the Las Vegas Strip. A rep told "—" for a shop there
    would think we had lost it, not that it lies outside any city limit."""
    assert bc.city_from(_places(designated=["Paradise CDP"])) == "Paradise"


def test_an_incorporated_place_outranks_a_designated_one():
    got = bc.city_from(_places(incorporated=["Carmel city"], designated=["Home Place CDP"]))
    assert got == "Carmel"


def test_the_suffix_is_stripped_but_a_name_that_ends_in_City_survives():
    """THE TRAP. Census writes the type in lower case after the name, so
    "Kansas City city" is Kansas City and "New York city" is New York. Strip
    case-insensitively and Kansas City becomes "Kansas"."""
    assert bc.clean_place("Kansas City city") == "Kansas City"
    assert bc.clean_place("New York city") == "New York"
    assert bc.clean_place("Chapel Hill town") == "Chapel Hill"
    assert bc.clean_place("Paradise CDP") == "Paradise"


def test_a_coordinate_inside_no_place_is_none_not_an_empty_string():
    """Rural addresses fall outside every incorporated place. None reads as
    "still unanswered" and a later run retries it; "" looks like a lookup that
    succeeded and found nothing."""
    assert bc.city_from(_places()) is None


# --- knowing a refusal from an answer --------------------------------------

def test_a_service_error_is_not_a_shop_without_a_town():
    """"filled 0, still unnamed 431" is what a broken lookup looked like the
    first time, and it reads as a fact about the shops. It is a fact about the
    service, and every remaining row would fail identically."""
    with pytest.raises(bc.LookupRefused):
        bc.check_status({"errors": ["benchmark is required"]})


def test_an_empty_result_is_an_answer_and_does_not_stop_the_run():
    bc.check_status(_places())


def test_the_run_stops_on_a_refusal_instead_of_asking_431_times(monkeypatch):
    asked = []

    def refuse(lat, lng):
        asked.append((lat, lng))
        return {"errors": ["service unavailable"]}

    rows = [SimpleNamespace(store_name=f"Shop {i}", city="",
                            latitude=1.0 + i, longitude=2.0) for i in range(6)]
    monkeypatch.setattr(bc, "pending", lambda db: rows)
    assert bc.run(SimpleNamespace(commit=lambda: None), lookup=refuse) == 0
    assert len(asked) == 1, "it must not ask for the other five"


# --- which rows may be asked about -----------------------------------------

def test_a_row_that_already_has_a_city_is_never_touched():
    """The sweep's own addr:city is the shop's tag and outranks a coordinate --
    and a backfill that overwrites cannot safely be re-run."""
    assert bc.pending_rows([SimpleNamespace(city="Naples", latitude=1.0, longitude=2.0)]) == []


def test_a_row_with_no_coordinates_cannot_be_asked():
    assert bc.pending_rows([SimpleNamespace(city="", latitude=None, longitude=None)]) == []


def test_a_row_with_a_coordinate_and_no_city_is_the_whole_point():
    row = SimpleNamespace(city="", latitude=1.0, longitude=2.0)
    assert bc.pending_rows([row]) == [row]
