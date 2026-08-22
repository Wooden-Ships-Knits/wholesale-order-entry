"""Persisting a sweep into `prospects`.

The mapping is pure and tested here without a database. The property that
actually matters — that re-running the sweep cannot erase a verdict somebody
paid for — is a fact about which columns the upsert is allowed to write, so it
is tested by inspecting that list rather than by needing Postgres.
"""
from app.db.models import Prospect
from app.maps import prospect_store as ps


ROW = {
    "osm_id": "node/13372898360", "place_id": "", "store_name": "Allure Glamour",
    "latitude": "33.818432", "longitude": "-117.2295092",
    "types": "clothes", "found_near": "Perris", "state": "CA", "rating": "",
    "review_count": "", "vicinity": "2560 N Perris Boulevard, Perris",
    "phone": "+1-951-216-3110", "website": "", "clothes": "wedding;women",
    "womenswear": "True", "second_hand": "", "instagram": "", "email": "",
    "opening_hours": "We-Mo 10:00-19:00", "postcode": "92571-3251",
    "nearest_stockist": "BELLE BOUTIQUE (CA)", "distance_miles": "24.3",
    "potential_conflict": "False", "drive_minutes": "",
}


# --- the rule the whole module exists for ----------------------------------

ASSESSMENT = ("verdict", "confidence", "for_the_rep", "reasons", "against",
              "store_type", "brand_count", "products_per_brand", "tag_lift",
              "price_median", "price_range", "knitwear_share",
              "knitwear_price_median", "signature_tags_carried",
              "knit_tags_carried", "knit_evidence", "problems", "assessed_at")


def test_a_sweep_may_not_write_any_assessment_column():
    """Re-running the sweep must not erase a verdict that cost a model call."""
    assert not set(ps.SWEEP_COLUMNS) & set(ASSESSMENT)


def test_the_mapping_itself_cannot_name_an_assessment_column():
    assert not set(ps.sweep_values(ROW)) & set(ASSESSMENT)


def test_a_sweep_does_not_reset_first_seen_at():
    """It records when we FIRST found the shop; a re-run has not re-found it
    for the first time."""
    assert "first_seen_at" not in ps.SWEEP_COLUMNS
    assert "last_seen_at" in ps.SWEEP_COLUMNS


def test_marks_are_untouchable_from_here():
    assert not any(c.startswith("mark") for c in ps.SWEEP_COLUMNS)


# --- the mapping ------------------------------------------------------------

def test_the_places_vocabulary_is_translated_not_dropped():
    """`found_near` and `vicinity` are what discover_osm kept for compatibility
    with the Places path. Guessing by name would silently lose town and street."""
    v = ps.sweep_values(ROW)
    assert v["city"] == "Perris"
    assert v["address"] == "2560 N Perris Boulevard, Perris"


def test_blank_cells_become_null_not_empty_string():
    v = ps.sweep_values(ROW)
    assert v["website"] is None
    assert v["rating"] is None
    assert v["review_count"] is None


def test_booleans_survive_being_csv_text():
    v = ps.sweep_values(ROW)
    assert v["womenswear"] is True
    assert v["potential_conflict"] is False


def test_a_blank_boolean_is_unknown_rather_than_false():
    v = ps.sweep_values({**ROW, "womenswear": ""})
    assert v["womenswear"] is None


def test_numbers_are_parsed():
    v = ps.sweep_values(ROW)
    assert v["latitude"] == 33.818432
    assert v["distance_miles"] == 24.3


def test_territory_is_stamped_when_given():
    """/reps filters on it, so a sweep loaded without one is invisible to reps."""
    assert ps.sweep_values(ROW, territory="FL - Jason")["territory"] == "FL - Jason"
    assert "territory" not in ps.sweep_values(ROW)


def test_state_is_carried_through():
    """The rep page reads `state`, and the sweep is the only thing that knows
    it: discover_osm queries one state at a time and stamps the code it asked
    for. Leaving it out of FIELDS dropped it silently -- the column stayed NULL
    on all 225 rows and nothing failed."""
    assert ps.sweep_values(ROW)["state"] == "CA"
    assert "state" in ps.SWEEP_COLUMNS


def test_a_row_naming_no_element_is_refused():
    assert ps.sweep_values({**ROW, "osm_id": ""}) is None


def test_a_nameless_shop_falls_back_to_its_osm_id():
    """store_name is NOT NULL, and "" would read as a shop called nothing."""
    assert ps.sweep_values({**ROW, "store_name": ""})["store_name"] == "node/13372898360"


def test_every_column_written_exists_on_the_model():
    columns = set(Prospect.__table__.columns.keys())
    assert set(ps.sweep_values(ROW, territory="X")) <= columns
    assert set(ps.SWEEP_COLUMNS) <= columns
