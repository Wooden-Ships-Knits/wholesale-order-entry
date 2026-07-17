# Nearby-Stockist Conflict Check API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/accounts/nearby` — K nearest wholesale stockists to a lat/lng with drive-time-based conflict verdict (default < 20 min), per `docs/superpowers/specs/2026-07-17-nearby-conflict-check-design.md`.

**Architecture:** Salesforce query (cached) → pure-Python haversine KNN pre-filter → one Google Distance Matrix call → verdict; straight-line fallback when Google is unavailable. New `app/geo/` package; route in `routers/accounts.py`; field names in `mapping.py`.

**Tech Stack:** FastAPI, simple-salesforce, requests, pytest (+ httpx for TestClient).

---

### Task 1: Salesforce mapping + geocoded-accounts query

**Files:** Modify `backend/app/salesforce/mapping.py`, `backend/app/salesforce/client.py`

- [ ] Add to `mapping.py`: `ACCOUNT_TYPE = "Type"`, `WHOLESALE_TYPE = "Wholesale"`, `SHIPPING_LAT = "ShippingLatitude"`, `SHIPPING_LNG = "ShippingLongitude"`, `NEARBY_ACCOUNT_FIELDS = ("Id", "Name", "ShippingCity", "ShippingState", SHIPPING_LAT, SHIPPING_LNG)`, and `map_nearby_account(record) -> {"accountId","name","cityState","lat","lng"}`.
- [ ] Add to `client.py`: `list_geocoded_wholesale_accounts()` — SOQL `SELECT <fields> FROM Account WHERE Type='Wholesale' AND ShippingLatitude != null AND ShippingLongitude != null`, wrapped in `_cached("geocoded_accounts", ...)`.
- [ ] Test `map_nearby_account` in `tests/test_geo_distance.py` (mapping is pure). Run pytest. Commit.

### Task 2: `app/geo/distance.py` (TDD)

- [ ] Failing tests in `tests/test_geo_distance.py`: haversine NYC↔LA ≈ 2446 mi (±1%), zero distance, short hop; `nearest_candidates` returns pool sorted ascending with `distanceMiles` rounded to 1 decimal.
- [ ] Implement `haversine_miles(lat1, lng1, lat2, lng2)` (R = 3958.8 mi) and `nearest_candidates(lat, lng, accounts, pool_size)`.
- [ ] pytest green. Commit.

### Task 3: `app/geo/drive_time.py` (TDD)

- [ ] Failing tests in `tests/test_drive_time.py` (mock `requests.get`): parses minutes (`round(duration.value/60)`), `None` for element status ≠ OK, raises `DriveTimeError` on top-level status ≠ OK / HTTP error / timeout.
- [ ] Implement `drive_minutes(origin, destinations, api_key, timeout=5.0) -> list[int | None]` — single Distance Matrix request, `mode=driving`.
- [ ] pytest green. Commit.

### Task 4: `app/geo/conflict.py` orchestrator (TDD)

- [ ] Failing tests in `tests/test_conflict.py` (monkeypatch `client.list_geocoded_wholesale_accounts` + `drive_time.drive_minutes` + settings key): drive-time verdict true/false at threshold, sort by minutes with `None` last, truncate to k, fallback mode on empty key and on `DriveTimeError` (verdict = distance < maxMinutes × 0.5).
- [ ] Implement `find_nearby(lat, lng, k, max_minutes) -> dict` per spec (`APPROX_MILES_PER_MINUTE = 0.5`).
- [ ] pytest green. Commit.

### Task 5: config + route + endpoint test

- [ ] `config.py`: `google_maps_server_api_key: str = ""`, `conflict_max_minutes: int = 20`. `.env.example`: both keys with comments (server key ≠ browser key; IP-restrict).
- [ ] `routers/accounts.py`: `GET /accounts/nearby` with validated Query params (`lat` −90…90, `lng` −180…180, `k` 1…25 default 5, `maxMinutes` 1…240 default None → settings), delegating to `conflict.find_nearby`.
- [ ] Add `httpx` to `requirements-dev.txt`; TestClient test: 200 happy path (patched), 422 on bad lat.
- [ ] pytest green. Commit.

### Task 6: docs

- [ ] architecture.md: API table row + short §5 note referencing the spec; §9 server-key note.
- [ ] CLAUDE.md: API surface row + env vars.
- [ ] PRD.md: new functional note (backend-only, UI undecided) + open item (where to surface).
- [ ] Commit.

### Task 7: verify live

- [ ] `docker compose build backend && docker compose up -d backend`.
- [ ] `curl /api/accounts/nearby?lat=…&lng=…` against the running stack → straight-line mode (no server key configured), real Salesforce data, sane distances; 422 case.
- [ ] Full pytest + `git status` clean. Push branch.
