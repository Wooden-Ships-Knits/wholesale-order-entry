from app.email import conflict_template
from app.routers.conflict_email import _state_from

NEIGHBORS = [
    {
        "name": "VAGABOND APPAREL BOUTIQUE",
        "driveMinutes": 8,
        "distanceMiles": 2.8,
        "lastOrderName": "F26 SWEATERS 11/01 - 11/20",
    },
    {
        "name": "LADY LANELL'S",
        "driveMinutes": 9,
        "distanceMiles": 3.6,
        "lastOrderName": "S26 SWEATERS 12/01 - 12/30",
    },
]


def test_rep_facing_draft_lists_conflicts():
    d = conflict_template.build(
        store_name="TAKE2 STAGING & DESIGN",
        rep_name="Jason Miller",
        state="FL",
        neighbors=NEIGHBORS,
        max_minutes=20,
    )
    # The email goes to the rep, whose address we don't store — admin fills it.
    assert d["to"] == ""
    assert d["subject"] == (
        "Wooden Ships wholesale inquiry — TAKE2 STAGING & DESIGN "
        "(potential conflict nearby)"
    )
    body = d["body"]
    assert body.startswith("Hi Jason,")
    assert "inquiry below from TAKE2 STAGING & DESIGN." in body
    assert "according to the state (FL)" in body
    assert "• VAGABOND APPAREL BOUTIQUE (8 min, 2.8 miles) - Last order: F26" in body
    assert "• LADY LANELL'S (9 min, 3.6 miles) - Last order: S26" in body
    assert body.endswith(
        "Please reach out to the account if you would like to work with them."
    )


def test_no_conflicts_message():
    d = conflict_template.build(store_name="New Store", rep_name="Jason", neighbors=[])
    assert "No nearby stockist conflicts were found" in d["body"]
    assert "•" not in d["body"]


def test_greeting_falls_back_without_rep():
    assert conflict_template.build(neighbors=[])["body"].startswith("Hi team,")


def test_rep_first_name_only():
    body = conflict_template.build(rep_name="  jason  miller ", neighbors=[])["body"]
    assert body.startswith("Hi jason,")


def test_metrics_without_drive_time_show_miles_only():
    d = conflict_template.build(
        neighbors=[
            {"name": "A PIED", "driveMinutes": None, "distanceMiles": 4.5, "lastOrderName": "F25 X"}
        ],
    )
    assert "A PIED (4.5 miles) - Last order: F25" in d["body"]


def test_season_falls_back_when_unparseable():
    d = conflict_template.build(
        neighbors=[
            {"name": "X", "driveMinutes": 3, "distanceMiles": 1.0, "lastOrderName": "MISC ORDER"}
        ],
    )
    assert "Last order: —" in d["body"]


def test_state_omitted_when_unknown():
    body = conflict_template.build(neighbors=NEIGHBORS)["body"]
    assert "potential conflicts nearby with the following accounts:" in body
    assert "according to the state" not in body


def test_state_from_parses_city_state_and_full_address():
    assert _state_from("Miami, FL") == "FL"
    assert _state_from("123 Main St, Brooklyn, NY 11201, USA") == "NY"
    assert _state_from("no state here") is None
    assert _state_from(None, "Austin, TX") == "TX"
