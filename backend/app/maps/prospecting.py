"""Find shops in a territory that could stock Wooden Ships and do not yet.

Design and reasoning: notebooks/PROSPECTING.md · flowchart: prospecting-flow.drawio

    import prospecting as p
    from app.salesforce import client
    sf = client._client()

    df = p.run(sf, "FL - Jason Hilsenrad", origins=p.FL_CITIES[:3])
    df.to_csv("fl-prospects.csv", index=False)

Order of operations is a cost decision, not a style one. Places Details and the
conflict check are both billed PER CANDIDATE; dedupe against Salesforce is free
and removes the most rows. So: discover → dedupe → details → conflict.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
import os, sys, certifi
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "backend").is_dir())
sys.path.insert(0, str(ROOT / "backend"))     # makes `app...` importable
os.chdir(ROOT)                                # pydantic-settings reads ./.env
    
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
os.environ.setdefault(
    "GOOGLE_CREDENTIALS_PATH",
    str(ROOT / "backend" / "credentials" / "dialy-report-automation-e20c53e67542.json"),
)
import pandas as pd

from app.config import settings
from app.geo import conflict as geo_conflict
from app.salesforce import mapping

PLACES = "https://maps.googleapis.com/maps/api/place"

# Search origins. Nearby Search returns 20 per page and 60 per origin at most,
# so coverage comes from MORE ORIGINS, never from a bigger radius.
# Population centres, not our own stores: searching around existing accounts
# only finds the places we already sell.
FL_CITIES = [
    ("Miami", 25.7617, -80.1918),
    ("Fort Lauderdale", 26.1224, -80.1373),
    ("West Palm Beach", 26.7153, -80.0534),
    ("Naples", 26.1420, -81.7948),
    ("Fort Myers", 26.6406, -81.8723),
    ("Sarasota", 27.3364, -82.5307),
    ("Tampa", 27.9506, -82.4572),
    ("St. Petersburg", 27.7676, -82.6403),
    ("Orlando", 28.5383, -81.3792),
    ("Winter Park", 28.6000, -81.3392),
    ("Jacksonville", 30.3322, -81.6557),
    ("Tallahassee", 30.4383, -84.2807),
    ("Gainesville", 29.6516, -82.3248),
    ("Vero Beach", 27.6386, -80.3973),
    ("Key West", 24.5551, -81.7800),
]

# Google's own categories. clothing_store is the anchor; the keyword widens it
# to the boutiques that are categorised loosely.
PLACE_TYPE = "clothing_store"
KEYWORDS = ("boutique", "women's clothing")

# Categories that are clothing-adjacent but not our customer.
REJECT_TYPES = {"shoe_store", "jewelry_store", "department_store", "supermarket"}

# Two shops closer than this, with similar names, are the same shop.
SAME_PLACE_METRES = 150
NAME_SIMILARITY = 0.82

# Words that carry no identity — every other boutique has them.
_NOISE = re.compile(r"\b(the|boutique|shop|store|co|inc|llc|ltd|and)\b")

_details_cache: dict[str, dict] = {}


# ------------------------------------------------------------------ helpers

def _norm(name: str) -> str:
    """'MORLEY(DELRAY BEACH)' -> 'morley'. Strips branch suffixes and noise
    words so a Salesforce name and a Google name can be compared."""
    n = (name or "").lower()
    n = re.sub(r"\(.*?\)", " ", n)          # "(DELRAY BEACH)" is a branch, not a name
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    n = _NOISE.sub(" ", n)
    return " ".join(n.split())


def _metres(lat1, lng1, lat2, lng2) -> float:
    """Haversine. Good to a few metres at these distances."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _get(path: str, params: dict) -> dict:
    params = {**params, "key": settings.google_maps_server_api_key}
    url = f"{PLACES}/{path}/json?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=25) as fh:
        return json.load(fh)


# ------------------------------------------------------------------- stages

def discover(origins, radius_m: int = 6000, verbose: bool = True) -> pd.DataFrame:
    """Places Nearby Search around each origin, deduped by place_id.

    Candidates repeat heavily between nearby origins, so dedupe here rather
    than paying for the same shop twice downstream.
    """
    seen: dict[str, dict] = {}
    for city, lat, lng in origins:
        found = 0
        for keyword in KEYWORDS:
            token, page = None, 0
            while page < 3:  # 3 pages x 20 = Google's 60-result ceiling
                params = (
                    {"pagetoken": token}
                    if token
                    else {"location": f"{lat},{lng}", "radius": radius_m,
                          "type": PLACE_TYPE, "keyword": keyword}
                )
                # A next_page_token is not valid immediately; Google returns
                # INVALID_REQUEST for a second or two after issuing it.
                if token:
                    time.sleep(2)
                data = _get("nearbysearch", params)
                if data.get("status") not in ("OK", "ZERO_RESULTS"):
                    raise RuntimeError(f"Places: {data.get('status')} {data.get('error_message','')}")
                for r in data.get("results", []):
                    types = set(r.get("types", []))
                    if types & REJECT_TYPES and PLACE_TYPE not in types:
                        continue
                    loc = r["geometry"]["location"]
                    seen.setdefault(r["place_id"], {
                        # "place_id": r["place_id"],
                        # "store_name": r["name"],
                        # "latitude": loc["lat"],
                        # "longitude": loc["lng"],
                        # "types": ",".join(sorted(types)),
                        # "found_near": city,
                        # # from the same response, no extra cost
                        # "rating": r.get("rating"),
                        # "reviews": r.get("user_ratings_total"),
                        # "business_status": r.get("business_status"),
                        # "vicinity": r.get("vicinity"),
                        # "phone": r.get("international_phone_number"),
                        "_raw": r,
                    })
                    found += 1
                token = data.get("next_page_token")
                page += 1
                if not token:
                    break
        if verbose:
            print(f"  {city:18} {found:4} hits   running unique: {len(seen)}")
    return pd.DataFrame(seen.values())


def existing_accounts(sf, territory: str) -> pd.DataFrame:
    """Active Salesforce accounts in the territory, with coordinates.

    Excludes the inactive/OOB ranks — the same list the conflict check ignores
    — but keeps unranked accounts, which are usually new stores rather than
    dead ones.
    """
    excluded = "','".join(mapping.EXCLUDED_RANKS)
    safe = territory.replace("\\", "\\\\").replace("'", r"\'")
    q = (
        "SELECT Id, Name, ShippingLatitude, ShippingLongitude, Rank__c FROM Account "
        f"WHERE SalesTerritory__c = '{safe}' "
        f"AND (Rank__c = null OR Rank__c NOT IN ('{excluded}'))"
    )
    recs = sf.query_all(q)["records"]
    df = pd.DataFrame(recs).drop(columns="attributes", errors="ignore")
    return df


def drop_existing(cands: pd.DataFrame, accounts: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Remove candidates that are already customers.

    Name OR proximity alone is not enough: 'MORLEY(DELRAY BEACH)' vs 'Morley'
    defeats exact matching, and two different boutiques can share a mall. A
    match is a close name AND close coordinates, or an unmistakable name at
    the same spot.
    """
    known = accounts.dropna(subset=["ShippingLatitude", "ShippingLongitude"])
    pairs = [(_norm(r.Name), r.ShippingLatitude, r.ShippingLongitude, r.Name)
             for r in known.itertuples()]

    keep, dropped = [], []
    for c in cands.itertuples():
        cn = _norm(c.store_name)
        hit = None
        for kn, klat, klng, raw in pairs:
            if _metres(c.latitude, c.longitude, klat, klng) > SAME_PLACE_METRES:
                continue
            if kn == cn or SequenceMatcher(None, kn, cn).ratio() >= NAME_SIMILARITY:
                hit = raw
                break
        (dropped if hit else keep).append((c.Index, hit))

    if verbose:
        print(f"  already customers: {len(dropped)}   new candidates: {len(keep)}")
        for idx, hit in dropped[:10]:
            print(f"     {cands.loc[idx, 'store_name'][:34]:36} = {hit}")
    return cands.loc[[i for i, _ in keep]].reset_index(drop=True)


def add_details(cands: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Place Details for the website + address. One billed call per candidate,
    so this runs AFTER dedupe. Cached by place_id for the session."""
    sites, addrs = [], []
    for pid in cands["place_id"]:
        if pid not in _details_cache:
            d = _get("details", {"place_id": pid,
                                 "fields": "website,formatted_address,formatted_phone_number"})
            _details_cache[pid] = d.get("result", {})
        r = _details_cache[pid]
        sites.append(r.get("website"))
        addrs.append(r.get("formatted_address"))
    out = cands.copy()
    out["website"] = sites
    out["address"] = addrs
    if verbose:
        print(f"  with a website: {out['website'].notna().sum()} of {len(out)}")
    return out


def add_conflict(cands: pd.DataFrame, k: int = 5, verbose: bool = True) -> pd.DataFrame:
    """potential_conflict via the app's own rule (app/geo/conflict.py).

    Reused rather than reimplemented so this list and the live order form can
    never disagree about what counts as a conflict. Billed per candidate
    (Distance Matrix), which is why it is last.

    NOTHING IS DROPPED on a conflict. The flag is information for the rep, who
    may well permit the store anyway — that judgement is theirs, and a list
    that silently removed the close ones would hide the decision instead of
    presenting it. Hence nearest_stockist / drive_minutes / distance_miles
    travel with the flag: "True" alone is not actionable.
    """
    flags, nearest, minutes, miles, modes = [], [], [], [], []
    for c in cands.itertuples():
        try:
            v = geo_conflict.find_nearby(c.latitude, c.longitude, k, settings.conflict_max_minutes)
        except Exception as exc:  # never let one lookup kill the run
            print(f"    conflict check failed for {c.store_name}: {exc}")
            flags.append(None); nearest.append(None); minutes.append(None)
            miles.append(None); modes.append(None)
            continue
        n = (v.get("neighbors") or [{}])[0]
        flags.append(v.get("conflict"))
        nearest.append(n.get("name"))
        # find_nearby's own key names — driveMinutes/distanceMiles, NOT
        # minutes/miles. Reading the wrong ones gives a silent column of None.
        minutes.append(n.get("driveMinutes"))
        miles.append(n.get("distanceMiles"))
        modes.append(v.get("mode"))
    out = cands.copy()
    out["potential_conflict"] = flags
    out["nearest_stockist"] = nearest
    out["drive_minutes"] = minutes
    out["distance_miles"] = miles
    if verbose:
        got = sum(1 for m in minutes if m is not None)
        print(f"  flagged as conflicting: {sum(1 for f in flags if f)} of {len(out)}"
              f"   ·  drive time on {got}/{len(out)}  (modes: {set(modes)})")
    return out


COLUMNS = [
    "store_name", "latitude", "longitude", "website", "potential_conflict",
    "nearest_stockist", "drive_minutes", "distance_miles", "address", "found_near",
    "types", "place_id","rating", "reviews", "business_status", "vicinity", "phone",
]


def plot(prospects: pd.DataFrame, accounts: pd.DataFrame, *, zoom: int | None = None):
    """Prospects (yellow) over existing accounts (grey), on one Leaflet map.

        m = p.plot(df, p.existing_accounts(sf, "FL - Jason Hilsenrad"))
        m.save("notebooks/fl-prospects.html")

    Both layers on one map on purpose: a prospect is only interesting in
    relation to who we already sell to nearby, and two separate maps make that
    comparison impossible to do by eye. Each layer can be toggled.
    """
    import folium
    from folium.plugins import MarkerCluster

    known = accounts.dropna(subset=["ShippingLatitude", "ShippingLongitude"])
    located = prospects.dropna(subset=["latitude", "longitude"])
    if located.empty and known.empty:
        raise ValueError("Nothing to plot — no coordinates on either set.")

    lats = list(located.latitude) + list(known.ShippingLatitude)
    lngs = list(located.longitude) + list(known.ShippingLongitude)
    m = folium.Map(
        location=[sum(lats) / len(lats), sum(lngs) / len(lngs)],
        zoom_start=zoom or 11,
        tiles="cartodbpositron",
    )
    if zoom is None:
        m.fit_bounds([[min(lats), min(lngs)], [max(lats), max(lngs)]])

    # Existing accounts first so they sit UNDER the prospects — the prospects
    # are what this map is for, and a grey pin drawn on top would hide one.
    existing_layer = folium.FeatureGroup(name=f"Existing accounts ({len(known)})")
    for r in known.itertuples():
        folium.CircleMarker(
            [r.ShippingLatitude, r.ShippingLongitude],
            radius=7, color="#6b6b6b", fill=True, fill_color="#9aa0a6",
            fill_opacity=0.9, weight=1,
            tooltip=f"{r.Name}  (existing)",
            popup=folium.Popup(
                f"<b>{r.Name}</b><br><span style='color:#666'>existing account"
                f"<br>{getattr(r, 'Rank__c', '') or 'no rank'}</span>", max_width=260),
        ).add_to(existing_layer)
    existing_layer.add_to(m)

    prospect_layer = folium.FeatureGroup(name=f"Prospects ({len(located)})")
    cluster = MarkerCluster().add_to(prospect_layer)
    for r in located.itertuples():
        conflict = bool(getattr(r, "potential_conflict", False))
        site = getattr(r, "website", None)
        near = getattr(r, "nearest_stockist", None)
        mins = getattr(r, "drive_minutes", None)
        note = (
            f"<br><span style='color:#b8860b'>conflict — {near}, {mins} min</span>"
            if conflict and near else ""
        )
        folium.CircleMarker(
            [r.latitude, r.longitude],
            radius=8, color="#d39700", fill=True, fill_color="#f2ff01",
            fill_opacity=0.95, weight=2,
            tooltip=f"{r.store_name}  (prospect)",
            popup=folium.Popup(
                f"<b>{r.store_name}</b><br>"
                + (f"<a href='{site}' target='_blank'>{site}</a>" if site else "no website")
                + note,
                max_width=280),
        ).add_to(cluster)
    prospect_layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    print(f"yellow = {len(located)} prospects · grey = {len(known)} existing accounts")
    return m


def run(sf, territory: str, origins=None, radius_m: int = 6000) -> pd.DataFrame:
    """The whole pipeline. Returns the Step 1 table."""
    origins = origins or FL_CITIES
    print(f"1. discovering around {len(origins)} origin(s)")
    cands = discover(origins, radius_m)
    print(f"2. dedupe against active accounts in {territory!r}")
    cands = drop_existing(cands, existing_accounts(sf, territory))
    if cands.empty:
        return pd.DataFrame(columns=COLUMNS)
    print("3. place details")
    cands = add_details(cands)
    print("4. conflict check")
    cands = add_conflict(cands)
    return cands[COLUMNS].sort_values(["potential_conflict", "store_name"]).reset_index(drop=True)
