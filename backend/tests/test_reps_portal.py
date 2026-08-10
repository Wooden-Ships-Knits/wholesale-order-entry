"""/api/reps-portal — sign-in, order ownership, and the payload allowlist."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.admin.security import hash_password, require_admin
from app.config import settings
from app.db.session import get_db
from app import reps_auth
from app.main import app
from app.reps_auth import REP_NAMES
from app.routers import reps_portal
from app.routers.reps_portal import _owns, _rep_row

# One password per rep — the whole point of the scheme is that Aviva's does not
# open Rande's dashboard, so the fixtures need two distinct ones.
PASSWORD = "aviva-test-pw"
RANDE_PASSWORD = "rande-test-pw"
AVIVA = "aviva@wooden-ships.com"
RANDE = "rande@wooden-ships.com"

WRITERS = {"Aviva Landin": AVIVA, "Rande Cohen": RANDE}
TERRITORIES = {"CA/ HI - Rande Cohen": RANDE, "Midwest - Aviva Landin": AVIVA}

# The age the cards report is measured against the real clock, so the fixtures
# have to be anchored to it rather than to a fixed calendar date.
NOW = datetime.now(timezone.utc)


def _order(**over):
    base = dict(
        id=uuid.UUID("2b1f9c4e-0000-0000-0000-000000000000"),
        created_at=NOW,
        season_code="F26",
        total_qty=24,
        total_amount=Decimal("1800.00"),
        ship_window="9/1-20",
        account_name="A Pied Boutique",
        buyer_name="Jane Buyer",  # part of the PDF filename
        order_written_by=None,
        sales_territory=None,
        notes=None,
        status="submitted",
        status_reason=None,
        status_at=None,
        signature_email=None,
        signature_requested_at=None,
        signature_token=None,
        signature_signed_at=None,
        signature_name=None,
        orig_total_qty=None,
        orig_total_amount=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _sheet_routing(monkeypatch):
    """The ownership rule over a test mapping, not the live Google Sheet.

    `rep_email_for_order` keeps the real shape of the rule — Written By first,
    Sales Territory as the fallback — so the tests assert the routing decision
    rather than the contents of somebody's spreadsheet.
    """
    monkeypatch.setattr(
        reps_portal.sheets_client,
        "rep_email_for_order",
        lambda written_by, territory: WRITERS.get(written_by) or TERRITORIES.get(territory),
    )
    monkeypatch.setattr(
        reps_portal.sheets_client, "rep_email_for_writer", lambda name: WRITERS.get(name)
    )


@pytest.fixture(autouse=True)
def _clear_login_guard():
    """The throttle is a module-level singleton, so failures from one test would
    otherwise count against the next and eventually lock the whole file out."""
    reps_portal.guard.reset()
    yield
    reps_portal.guard.reset()


@pytest.fixture(autouse=True)
def _isolate_dependency_overrides():
    """Undo this module's overrides, and any admin bypass another module left.

    test_conflict_email sets `dependency_overrides[require_admin]` at import
    time and never removes it, so without this the admin-boundary tests below
    would pass or fail depending on collection order.
    """
    admin_override = app.dependency_overrides.pop(require_admin, None)
    yield
    app.dependency_overrides.pop(get_db, None)
    if admin_override is not None:
        app.dependency_overrides[require_admin] = admin_override


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        settings,
        "reps_password_hashes",
        json.dumps(
            {
                "avivalandin": hash_password(PASSWORD),
                "randecohen": hash_password(RANDE_PASSWORD),
            }
        ),
    )
    # https base URL, because SessionMiddleware is built with https_only=True
    # (the production default, baked in at import time). Over http:// the
    # client discards the Secure cookie and every signed-in test looks logged
    # out. Plain constructor rather than a context manager: entering one runs
    # the app lifespan and starts the hourly signature-reminder loop, which
    # these tests have no use for.
    return TestClient(app, base_url="https://testserver")


def _sign_in(client, name="Aviva Landin", password=PASSWORD):
    return client.post("/api/reps-portal/login", json={"name": name, "password": password})


def _stub_orders(orders, by_id=None):
    """Serve a fixed list of orders instead of querying Postgres.

    `by_id` backs db.get(), which the PDF route uses to look one order up.
    """
    class _Result:
        def scalars(self):
            return iter(orders)

    class _Db:
        def execute(self, _stmt):
            return _Result()

        def get(self, _model, pk):
            return (by_id or {}).get(str(pk))

    app.dependency_overrides[get_db] = lambda: _Db()


# ------------------------------------------------------------------- login

def test_names_lists_the_roster(client):
    assert client.get("/api/reps-portal/names").json()["names"] == list(REP_NAMES)


def test_login_succeeds_for_a_known_rep(client):
    r = _sign_in(client)
    assert r.status_code == 200
    assert r.json()["name"] == "Aviva Landin"
    assert client.get("/api/reps-portal/session").json() == {
        "authenticated": True,
        "name": "Aviva Landin",
    }


def test_login_rejects_a_name_outside_the_roster(client):
    assert _sign_in(client, name="Mallory Nobody").status_code == 401
    assert client.get("/api/reps-portal/session").json()["authenticated"] is False


def test_login_rejects_a_wrong_password(client):
    assert _sign_in(client, password="wrong").status_code == 401


def test_a_bad_name_and_a_bad_password_are_indistinguishable(client):
    bad_name = _sign_in(client, name="Mallory Nobody")
    bad_pass = _sign_in(client, password="wrong")
    assert bad_name.json()["detail"] == bad_pass.json()["detail"]


def test_login_is_disabled_when_no_hashes_are_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "reps_password_hashes", "")
    assert _sign_in(client).status_code == 503


# ------------------------------------- one password per rep (revised 2026-08-10)

def test_a_reps_password_does_not_open_another_reps_dashboard(client):
    """The reason per-rep hashes exist. Under the old shared password this was a
    successful sign-in as Rande, and his whole book with it."""
    assert _sign_in(client, name="Rande Cohen", password=PASSWORD).status_code == 401


def test_each_rep_signs_in_with_their_own_password(client):
    assert _sign_in(client, name="Rande Cohen", password=RANDE_PASSWORD).status_code == 200
    assert client.get("/api/reps-portal/session").json()["name"] == "Rande Cohen"


def test_a_rep_with_no_hash_entry_cannot_sign_in(client):
    """On the roster but absent from REPS_PASSWORD_HASHES — no password works."""
    assert _sign_in(client, name="Kitty Tally", password=PASSWORD).status_code == 401
    assert _sign_in(client, name="Kitty Tally", password=RANDE_PASSWORD).status_code == 401


def test_a_hash_entry_off_the_roster_is_ignored(client, monkeypatch):
    """A stale entry must not outlive the name's removal from REP_NAMES."""
    monkeypatch.setattr(
        settings, "reps_password_hashes", json.dumps({"formerrep": hash_password("x")})
    )
    assert _sign_in(client, name="Former Rep", password="x").status_code == 401


def test_malformed_hashes_disable_sign_in_without_crashing(client, monkeypatch):
    """A typo in one env value must not take the order form down with it."""
    monkeypatch.setattr(settings, "reps_password_hashes", "{not json")
    assert _sign_in(client).status_code == 401
    assert client.get("/api/health").status_code == 200


def test_repeated_failures_are_throttled(client):
    """word-NN passwords are only safe against a script because of this."""
    for _ in range(reps_portal.guard._max_per_ip):
        assert _sign_in(client, password="wrong").status_code == 401
    blocked = _sign_in(client, password="wrong")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_the_throttle_outranks_a_correct_password(client):
    """Checked before verification, so a locked-out attacker cannot tell a
    right guess from a wrong one."""
    for _ in range(reps_portal.guard._max_per_ip):
        _sign_in(client, password="wrong")
    assert _sign_in(client, password=PASSWORD).status_code == 429


def test_a_successful_sign_in_clears_the_throttle(client):
    """A rep who mistypes a few times then gets it right is not locked out."""
    for _ in range(reps_portal.guard._max_per_ip - 1):
        _sign_in(client, password="wrong")
    assert _sign_in(client).status_code == 200
    for _ in range(reps_portal.guard._max_per_ip - 1):
        _sign_in(client, password="wrong")
    assert _sign_in(client).status_code == 200


def test_the_name_lookup_tolerates_spacing_and_case():
    raw = json.dumps({"avivalandin": hash_password(PASSWORD)})
    assert reps_auth.verify_rep("Aviva Landin", PASSWORD, raw) is True
    assert reps_auth.verify_rep("Aviva Landin", "wrong", raw) is False


def test_logout_ends_the_session(client):
    _sign_in(client)
    client.post("/api/reps-portal/logout")
    assert client.get("/api/reps-portal/session").json()["authenticated"] is False


def test_orders_require_sign_in(client):
    assert client.get("/api/reps-portal/orders").status_code == 401


# --------------------------------------------------- the two sessions are separate

def test_a_rep_session_cannot_reach_the_admin_api(client):
    _sign_in(client)
    assert client.get("/api/admin/orders").status_code == 401


def test_an_admin_session_cannot_reach_the_rep_api(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_password_hash", hash_password("admin-secret"))
    assert client.post("/api/admin/login", json={"password": "admin-secret"}).status_code == 200
    assert client.get("/api/reps-portal/orders").status_code == 401


# --------------------------------------------------------------- ownership

def test_written_by_wins_over_the_territory():
    """The 2026-08-06 rule: a rep who writes an order outside their own patch
    still owns it, and the territory owner does not."""
    o = _order(order_written_by="Aviva Landin", sales_territory="CA/ HI - Rande Cohen")
    assert _owns(o, AVIVA) is True
    assert _owns(o, RANDE) is False


def test_a_customer_filled_order_falls_through_to_the_territory_owner():
    o = _order(order_written_by=None, sales_territory="CA/ HI - Rande Cohen")
    assert _owns(o, RANDE) is True
    assert _owns(o, AVIVA) is False


def test_an_unroutable_order_belongs_to_nobody():
    assert _owns(_order(), AVIVA) is False


def test_the_list_shows_only_the_signed_in_reps_orders(client):
    _stub_orders(
        [
            _order(order_written_by="Aviva Landin", account_name="Mine"),
            _order(order_written_by="Rande Cohen", account_name="Theirs"),
            _order(sales_territory="Midwest - Aviva Landin", account_name="My territory"),
        ]
    )
    _sign_in(client)
    body = client.get("/api/reps-portal/orders").json()
    assert [o["accountName"] for o in body["orders"]] == ["Mine", "My territory"]
    assert body["rep"] == "Aviva Landin"


def test_a_rep_with_no_sheet_address_sees_nothing(client, monkeypatch):
    """Fail closed: without an address there is no way to tell this rep's orders
    from anyone else's, and the fallback must not be the whole customer book."""
    monkeypatch.setattr(reps_portal.sheets_client, "rep_email_for_writer", lambda name: None)
    _stub_orders([_order(order_written_by="Aviva Landin")])

    _sign_in(client)
    body = client.get("/api/reps-portal/orders").json()
    assert body["orders"] == []
    assert body["message"]


# ------------------------------------------------------------ metric cards

def _book():
    """One rep's book covering every state the cards count."""
    return [
        # signed on the form, accepted
        _order(order_written_by="Aviva Landin", total_qty=10, status="accepted"),
        # awaiting signature, link sent 12 days ago
        _order(
            order_written_by="Aviva Landin",
            total_qty=20,
            signature_email="a@b.com",
            signature_requested_at=NOW - timedelta(days=12),
            signature_token="tok",
        ),
        # awaiting signature, the send failed (no requested_at) — 3 days old
        _order(
            created_at=NOW - timedelta(days=3),
            order_written_by="Aviva Landin",
            total_qty=30,
            signature_token="tok2",
        ),
        # signed through the link, declined
        _order(
            order_written_by="Aviva Landin",
            total_qty=40,
            signature_signed_at=NOW - timedelta(days=1),
            status="declined",
        ),
        # somebody else's — must not be counted
        _order(order_written_by="Rande Cohen", total_qty=999, status="accepted"),
    ]


def test_counts_cover_every_card(client):
    _stub_orders(_book())
    _sign_in(client)
    counts = client.get("/api/reps-portal/orders").json()["counts"]
    assert counts["total"] == 4  # Rande's order excluded
    assert counts["totalQty"] == 100  # 10 + 20 + 30 + 40, not 999
    assert counts["awaitingSignature"] == 2
    assert counts["signatureNotSent"] == 1
    assert counts["oldestAwaitingDays"] == 12
    assert counts["awaitingReview"] == 2
    assert counts["accepted"] == 1
    assert counts["declined"] == 1


def test_counts_describe_the_whole_book_even_when_filtered(client):
    """The point of the cards: selecting one status must not zero out the rest.
    Without this the strip stops being a summary the moment it is used."""
    _stub_orders(_book())
    _sign_in(client)
    body = client.get("/api/reps-portal/orders?status_filter=accepted").json()
    assert len(body["orders"]) == 1  # the table narrows
    assert body["counts"]["total"] == 4  # the cards do not
    assert body["counts"]["declined"] == 1


def test_the_status_filter_still_narrows_the_rows(client):
    _stub_orders(_book())
    _sign_in(client)
    body = client.get("/api/reps-portal/orders?status_filter=declined").json()
    assert [o["totalQty"] for o in body["orders"]] == [40]


def test_counts_are_zero_for_an_empty_book(client):
    _stub_orders([])
    _sign_in(client)
    counts = client.get("/api/reps-portal/orders").json()["counts"]
    assert counts["total"] == 0
    assert counts["totalQty"] == 0
    assert counts["oldestAwaitingDays"] is None


def test_an_unresolvable_rep_still_gets_a_counts_block(client, monkeypatch):
    """The page renders the cards unconditionally, so the shape must not vary."""
    monkeypatch.setattr(reps_portal.sheets_client, "rep_email_for_writer", lambda name: None)
    _sign_in(client)
    assert client.get("/api/reps-portal/orders").json()["counts"]["total"] == 0


def test_a_signed_order_is_not_awaiting_signature():
    o = _order(signature_signed_at=NOW, signature_email="a@b.com")
    assert reps_portal._awaiting_signature(o) is False


def test_an_order_signed_on_the_form_is_not_awaiting_signature():
    assert reps_portal._awaiting_signature(_order()) is False


def test_the_response_is_capped(client):
    _stub_orders([_order(order_written_by="Aviva Landin") for _ in range(5)])
    _sign_in(client)
    body = client.get("/api/reps-portal/orders?limit=2").json()
    assert len(body["orders"]) == 2


# ------------------------------------------------------- the payload allowlist

# The exact keys a rep may receive. This test is the guard rail: it fails the
# moment _rep_row starts emitting card, conflict, certificate, Salesforce or
# dollar fields, which is precisely how a "just add one column" change would
# otherwise leak them.
REP_ROW_KEYS = {
    "id",
    "shortId",
    "createdAt",
    "seasonCode",
    "totalQty",
    "shipWindow",
    "accountName",
    "orderWrittenBy",
    "salesTerritory",
    "notes",
    "status",
    "statusReason",
    "statusAt",
    "signatureRequested",
    "signatureEmailSent",
    "signatureEmail",
    "signatureSignedAt",
    "signatureName",
    "signatureEdited",
    "origTotalQty",
}


def test_rep_row_emits_exactly_the_allowed_keys():
    assert set(_rep_row(_order())) == REP_ROW_KEYS


def test_the_endpoint_serializes_exactly_the_allowed_keys(client):
    """Same guarantee, asserted on the wire rather than on the helper."""
    _stub_orders([_order(order_written_by="Aviva Landin")])
    _sign_in(client)
    assert set(client.get("/api/reps-portal/orders").json()["orders"][0]) == REP_ROW_KEYS


def test_rep_row_carries_no_money():
    """The id IS present (the Order ID cell links to the PDF), but no dollar
    figures — quantity is on the rep's column list, money is not."""
    row = _rep_row(_order())
    assert row["shortId"] == "2b1f9c4e"
    assert row["id"] == str(_order().id)
    assert not any("amount" in key.lower() for key in row)


# ------------------------------------------------------------------ order PDF

def _pdf_fixture(tmp_path, monkeypatch, order):
    """Put a file where the PDF route will look for this order's copy."""
    from app.pdf import render as pdf_render

    monkeypatch.setattr(settings, "pdf_output_dir", str(tmp_path))
    name = pdf_render.order_pdf_filename(
        order.season_code, order.buyer_name or "", order.created_at, order.id
    )
    (tmp_path / name).write_bytes(b"%PDF-1.4 fake")
    return name


def test_a_rep_can_open_their_own_order_pdf(client, tmp_path, monkeypatch):
    mine = _order(order_written_by="Aviva Landin")
    _pdf_fixture(tmp_path, monkeypatch, mine)
    _stub_orders([mine], by_id={str(mine.id): mine})

    _sign_in(client)
    r = client.get(f"/api/reps-portal/orders/{mine.id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


def test_a_rep_cannot_open_another_reps_order_pdf(client, tmp_path, monkeypatch):
    """404 rather than 403 — a rep should not be able to probe which order ids
    exist outside their own book."""
    theirs = _order(order_written_by="Rande Cohen")
    _pdf_fixture(tmp_path, monkeypatch, theirs)
    _stub_orders([theirs], by_id={str(theirs.id): theirs})

    _sign_in(client)  # signed in as Aviva
    assert client.get(f"/api/reps-portal/orders/{theirs.id}/pdf").status_code == 404


def test_the_order_pdf_requires_a_rep_session(client):
    _stub_orders([])
    assert client.get(f"/api/reps-portal/orders/{uuid.uuid4()}/pdf").status_code == 401


def test_an_unknown_order_id_is_a_404(client):
    _stub_orders([])
    _sign_in(client)
    assert client.get(f"/api/reps-portal/orders/{uuid.uuid4()}/pdf").status_code == 404


def test_there_is_no_full_card_copy_route_for_reps(client, tmp_path, monkeypatch):
    """?full=1 is an admin-only concept; the rep route must ignore it and serve
    the masked copy rather than growing a second meaning."""
    mine = _order(order_written_by="Aviva Landin")
    name = _pdf_fixture(tmp_path, monkeypatch, mine)
    _stub_orders([mine], by_id={str(mine.id): mine})

    _sign_in(client)
    r = client.get(f"/api/reps-portal/orders/{mine.id}/pdf?full=1")
    assert r.status_code == 200
    assert r.content == (tmp_path / name).read_bytes()  # the masked file, not a card copy


def test_signature_not_required_when_the_form_was_signed_on_the_spot():
    assert _rep_row(_order())["signatureRequested"] is False


def test_signature_signed_state():
    row = _rep_row(
        _order(
            signature_email="buyer@store.com",
            signature_requested_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            signature_signed_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            signature_name="Jane Buyer",
        )
    )
    assert row["signatureRequested"] is True
    assert row["signatureEmailSent"] is True
    assert row["signatureName"] == "Jane Buyer"
    assert row["signatureEdited"] is False


def test_signature_awaiting_but_never_sent():
    """A token without a sent timestamp means the send failed at submit."""
    row = _rep_row(_order(signature_token="tok"))
    assert row["signatureRequested"] is True
    assert row["signatureEmailSent"] is False


def test_signature_edited_when_the_buyer_changed_the_quantities():
    row = _rep_row(
        _order(
            total_qty=22,
            orig_total_qty=40,
            orig_total_amount=Decimal("3000.00"),
            signature_signed_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        )
    )
    assert row["signatureEdited"] is True
    assert row["origTotalQty"] == 40


def test_signature_edited_is_false_when_the_order_was_signed_unchanged():
    row = _rep_row(_order(orig_total_qty=24, orig_total_amount=Decimal("1800.00")))
    assert row["signatureEdited"] is False


# ----------------------------------------------------- roster ↔ sheet agreement

@pytest.mark.skipif(
    not settings.region_rep_territories_sheet_id,
    reason="needs the live region/rep sheet (REGION_REP_TERRITORIES_SHEET_ID)",
)
def test_every_roster_name_resolves_to_an_address(monkeypatch):
    """A name in REP_NAMES the sheet doesn't know sees an empty dashboard.

    Hits the real sheet on purpose — a stub here would only assert that the
    constant equals itself. Skipped when the sheet isn't configured, so it runs
    against a real environment and never blocks an offline test run.
    """
    monkeypatch.undo()  # drop _sheet_routing's stubs; this one wants the real thing
    from app.sheets import client as real_sheets

    unresolved = [name for name in REP_NAMES if not real_sheets.rep_email_for_writer(name)]
    assert not unresolved, f"not in the sheet's Name column: {unresolved}"
