"""Which of the 3 newest seasons the order form shows, as ticked in /admin."""
import json

import pytest
from fastapi.testclient import TestClient

from app.admin.security import require_admin
from app.config import settings
from app.main import app
from app.salesforce import client as sf_client
from app.services import form_seasons

BOOKS = [{"Name": f"{c} Wholesale", "Id": c} for c in ["F25", "S27", "F26", "S26", "F27"]]
NEWEST3 = ["F27", "S27", "F26"]


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "settings" / "order_form_seasons.json"
    monkeypatch.setattr(settings, "form_seasons_file", str(path))
    return path


@pytest.fixture
def api(store, monkeypatch):
    monkeypatch.setattr(sf_client, "list_wholesale_pricebooks", lambda: BOOKS)
    # Other test modules set this override at import time; restore, don't pop.
    before = app.dependency_overrides.get(require_admin)
    app.dependency_overrides[require_admin] = lambda: None
    yield TestClient(app)
    if before is None:
        app.dependency_overrides.pop(require_admin, None)
    else:
        app.dependency_overrides[require_admin] = before


def codes(resp):
    return [s["code"] for s in resp.json()["seasons"]]


def test_no_file_shows_all_three_newest(api):
    assert codes(api.get("/api/seasons")) == NEWEST3


def test_unticking_hides_it_from_the_order_form(api, store):
    r = api.post("/api/admin/catalog/seasons", json={"season_code": "F26", "on_form": False})
    assert r.status_code == 200
    assert codes(api.get("/api/seasons")) == ["F27", "S27"]
    assert json.loads(store.read_text()) == ["F26"]


def test_ticking_it_again_brings_it_back(api, store):
    store.parent.mkdir(parents=True)
    store.write_text('["F26"]')
    api.post("/api/admin/catalog/seasons", json={"season_code": "F26", "on_form": True})
    assert codes(api.get("/api/seasons")) == NEWEST3
    assert json.loads(store.read_text()) == []


def test_admin_sees_only_the_three_newest(api, store):
    store.parent.mkdir(parents=True)
    store.write_text('["S27"]')
    body = api.get("/api/admin/catalog/seasons").json()
    assert {s["code"]: s["onForm"] for s in body["seasons"]} == {"F27": True, "S27": False, "F26": True}


def test_an_older_season_has_no_checkbox(api):
    r = api.post("/api/admin/catalog/seasons", json={"season_code": "S26", "on_form": True})
    assert r.status_code == 400


def test_the_last_season_cannot_be_unticked(api, store):
    store.parent.mkdir(parents=True)
    store.write_text('["F27", "S27"]')
    r = api.post("/api/admin/catalog/seasons", json={"season_code": "F26", "on_form": False})
    assert r.status_code == 400
    assert "At least one" in r.json()["detail"]
    assert json.loads(store.read_text()) == ["F27", "S27"]


def test_a_new_season_appears_without_anyone_ticking_it(store):
    # S26 was unticked; F27's price book goes live and pushes S26 out of the 3.
    store.parent.mkdir(parents=True)
    store.write_text('["F26"]')
    cands = form_seasons.candidates(["F27", "S27", "F26", "S26"])
    assert form_seasons.shown(cands, form_seasons.hidden_codes()) == ["F27", "S27"]


def test_codes_that_aged_out_are_dropped_on_save(store):
    store.parent.mkdir(parents=True)
    store.write_text('["S25"]')
    form_seasons.set_shown("F26", False, NEWEST3)
    assert json.loads(store.read_text()) == ["F26"]


def test_unreadable_file_shows_all_three(store):
    store.parent.mkdir(parents=True)
    store.write_text("not json")
    assert form_seasons.hidden_codes() == set()


def test_limit_zero_still_returns_every_season(api, store):
    store.parent.mkdir(parents=True)
    store.write_text('["F27"]')
    assert len(codes(api.get("/api/seasons?limit=0"))) == 5
