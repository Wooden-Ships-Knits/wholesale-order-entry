from fastapi.testclient import TestClient

from app.admin.security import require_admin
from app.email import conflict_template
from app.main import app
from app.routers.conflict_email import _state_from

app.dependency_overrides[require_admin] = lambda: None
client = TestClient(app)

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
        address="123 Main St, Miami, FL 33101",
        rep_name="Jason Miller",
        state="FL",
        neighbors=NEIGHBORS,
        max_minutes=20,
    )
    # The email goes to the rep, whose address we don't store — admin fills it.
    assert d["to"] == ""
    assert d["subject"] == "CONFLICT Inquiry — TAKE2 STAGING & DESIGN"
    body = d["body"]
    assert body.startswith("Hi,")
    assert "We received an order from this account." in body
    # Account block: name then address, on their own lines.
    assert "TAKE2 STAGING & DESIGN\n123 Main St, Miami, FL 33101" in body
    assert "There are potential conflicts with the following accounts:" in body
    assert "• VAGABOND APPAREL BOUTIQUE (8 min, 2.8 miles) - Last order: F26" in body
    assert "• LADY LANELL'S (9 min, 3.6 miles) - Last order: S26" in body
    assert "Please review this potential conflict and let us know if we may proceed." in body
    assert body.endswith("Thanks!")


def test_build_appends_order_token_to_subject():
    # The token lets a reply be correlated to the order even if it comes back to
    # the bare wholesale@ address (no plus-token). See app/email/inbound.py.
    oid = "9548e8ee-1234-4abc-8def-0123456789ab"
    d = conflict_template.build(store_name="TES2", order_id=oid, neighbors=NEIGHBORS)
    # Kind-tagged so a tax-cert subject token can't be mistaken for a conflict.
    assert d["subject"] == f"CONFLICT Inquiry — TES2 [#conflict-{oid}]"


def test_build_without_order_id_has_no_token():
    d = conflict_template.build(store_name="TES2", neighbors=NEIGHBORS)
    assert "[#" not in d["subject"]


def test_greeting_is_always_plain_hi():
    # Greeting is a fixed "Hi," — rep/territory no longer personalize it.
    d = conflict_template.build(
        store_name="Some Store",
        rep_name="Jason Miller",
        sales_territory="New England - Kitty Tally",
        neighbors=NEIGHBORS,
    )
    assert d["body"].startswith("Hi,")
    assert "Kitty Tally" not in d["body"]
    assert "Jason" not in d["body"]


def test_endpoint_prefers_account_name_over_buyer_name():
    # No lat/lng -> no nearby lookup; store identity comes from accountName.
    resp = client.post(
        "/api/conflict-email",
        json={"storeName": "Jane Smith", "accountName": "A Pied Boutique"},
    )
    assert resp.status_code == 200
    d = resp.json()
    assert "A Pied Boutique" in d["subject"]
    assert "A Pied Boutique" in d["body"]
    assert "Jane Smith" not in d["subject"]


def test_endpoint_falls_back_to_buyer_name_without_account_name():
    resp = client.post("/api/conflict-email", json={"storeName": "Jane Smith"})
    assert resp.status_code == 200
    assert "Jane Smith" in resp.json()["subject"]


def test_no_conflicts_message():
    d = conflict_template.build(store_name="New Store", rep_name="Jason", neighbors=[])
    assert "No nearby stockist conflicts were found" in d["body"]
    assert "•" not in d["body"]


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


def test_conflict_line_is_fixed_regardless_of_state():
    # State no longer changes the conflict line — it's always the same sentence.
    body = conflict_template.build(state="FL", neighbors=NEIGHBORS)["body"]
    assert "There are potential conflicts with the following accounts:" in body
    assert "according to the state" not in body


def test_account_block_omitted_without_name_or_address():
    body = conflict_template.build(neighbors=NEIGHBORS)["body"]
    # No store/address -> straight from the intro to the conflict line.
    assert "We received an order from this account.\n\nThere are potential" in body


def test_state_from_parses_city_state_and_full_address():
    assert _state_from("Miami, FL") == "FL"
    assert _state_from("123 Main St, Brooklyn, NY 11201, USA") == "NY"
    assert _state_from("no state here") is None
    assert _state_from(None, "Austin, TX") == "TX"
