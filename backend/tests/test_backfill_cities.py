"""Filling the city on rows that have coordinates but no place name.

431 of 1,437 prospects draw on the map and read "—" in the Where column: OSM
gave them a location but no addr:city tag, and their `address` is a street line
with no town in it ("7601 Windrose Avenue"). The only thing left to ask is the
coordinate itself.

The network is injected, so nothing here opens a socket or needs a key.
"""
import pytest

from types import SimpleNamespace

from app.maps import backfill_cities as bc


def _result(*types_and_names, status="OK"):
    """One Geocoding API result, in the shape Google returns."""
    return {"status": status, "results": [{"address_components": [
        {"long_name": name, "types": [t]} for t, name in types_and_names]}]}


def test_the_city_is_the_locality():
    got = bc.city_from(_result(("street_number", "7601"), ("route", "Windrose Avenue"),
                               ("locality", "Plano"), ("administrative_area_level_1", "Texas")))
    assert got == "Plano"


def test_a_postal_town_answers_when_there_is_no_locality():
    """Google files some places under postal_town instead — a row that reads
    "—" because we only looked for one spelling is a gap we created."""
    assert bc.city_from(_result(("postal_town", "Brighton"))) == "Brighton"


def test_an_unincorporated_place_falls_back_rather_than_staying_blank():
    got = bc.city_from(_result(("sublocality_level_1", "Bay Terraces"),
                               ("administrative_area_level_2", "San Diego County")))
    assert got == "Bay Terraces"


def test_a_county_is_not_a_city():
    """administrative_area_level_2 is a county. Writing "San Diego County" into
    a column a rep reads as a town is worse than leaving it empty."""
    assert bc.city_from(_result(("administrative_area_level_2", "San Diego County"))) is None


def test_no_result_is_none_not_an_empty_string():
    """None means "still unanswered" and a later run retries it. '' would look
    like a city we had already looked up and found to be nothing."""
    assert bc.city_from({"status": "ZERO_RESULTS", "results": []}) is None


def test_a_row_that_already_has_a_city_is_never_touched():
    """The sweep's own addr:city is the shop's own tag and outranks a guess
    from a coordinate — and a backfill that overwrites cannot be re-run."""
    rows = [SimpleNamespace(city="Naples", latitude=1.0, longitude=2.0)]
    assert bc.pending_rows(rows) == []


def test_a_row_with_no_coordinates_cannot_be_asked():
    rows = [SimpleNamespace(city="", latitude=None, longitude=None)]
    assert bc.pending_rows(rows) == []


def test_a_refused_request_is_not_a_shop_without_a_town():
    """"filled 0, still unnamed 431" is what a wrong API key looked like the
    first time, and it reads as a fact about the shops. It is a fact about our
    configuration, and every remaining row would fail identically."""
    with pytest.raises(bc.LookupRefused) as exc:
        bc.check_status({"status": "REQUEST_DENIED",
                         "error_message": "API keys with referer restrictions "
                                          "cannot be used with this API."})
    assert "referer" in str(exc.value)


def test_zero_results_is_an_answer_and_does_not_stop_the_run():
    """A coordinate in open water genuinely has no town. That must not look
    like a broken key and halt the other 430 rows."""
    bc.check_status({"status": "ZERO_RESULTS", "results": []})


def test_the_run_stops_on_a_refusal_instead_of_asking_431_times(monkeypatch):
    asked = []

    def refuse(lat, lng):
        asked.append((lat, lng))
        return {"status": "REQUEST_DENIED", "error_message": "bad key"}

    rows = [SimpleNamespace(store_name=f"Shop {i}", city="",
                            latitude=1.0 + i, longitude=2.0) for i in range(6)]
    monkeypatch.setattr(bc, "pending", lambda db: rows)
    filled = bc.run(SimpleNamespace(commit=lambda: None), lookup=refuse)
    assert filled == 0
    assert len(asked) == 1, "it must not pay for the other five"
