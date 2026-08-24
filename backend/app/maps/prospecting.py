"""Find shops in a territory that could stock Wooden Ships and do not yet.

Design and reasoning: notebooks/PROSPECTING.md · flowchart: prospecting-flow.drawio

    from app.maps import prospecting as p
    from app.salesforce import client
    sf = client._client()

    df = p.run(sf, "FL - Jason Hilsenrad", origins=p.FL_CITIES[:3])
    df.to_csv("fl-prospects.csv", index=False)

This module imports cleanly anywhere the `app` package is importable — it does
NOT set sys.path, chdir, or touch os.environ. That bootstrap belongs in the
notebook that calls it: doing it at import time made the module unimportable
in the container (no ../backend to find), changed the whole process's working
directory as a side effect, and broke %autoreload, because a reloaded module
re-ran it.

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
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

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

# Hosts that identify a platform, not a shop. Half the boutiques in the state
# list the same Facebook or Linktree page, so matching on these would collapse
# unrelated stores onto each other.
_NOT_IDENTITY = {
    "facebook.com", "m.facebook.com", "instagram.com", "linktr.ee",
    "twitter.com", "x.com", "tiktok.com", "yelp.com", "google.com",
    "sites.google.com", "wixsite.com", "square.site", "shopify.com",
}

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


def _phone_key(value) -> str | None:
    """'(561) 555-0100' / '+1 561-555-0100' -> '5615550100'.

    Ten digits or nothing: a partial number is not an identifier, and a short
    string would match far too eagerly.
    """
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def _domain_key(value) -> str | None:
    """'https://www.Shop.com/about' -> 'shop.com'. None for platform pages."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if "//" not in raw:
        raw = "//" + raw               # bare 'shop.com' has no scheme to split on
    host = urllib.parse.urlsplit(raw).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host if host and host not in _NOT_IDENTITY else None


def _first(row, *names):
    """First present, non-null attribute of a namedtuple row.

    The candidate frame changes shape along the pipeline — OSM gives `phone`,
    Place Details gives `phone_local` — so identity lookups read whichever
    exists rather than assuming one stage has already run.
    """
    for n in names:
        v = getattr(row, n, None)
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return v
    return None


def _unique_index(pairs) -> dict:
    """key -> account name, keeping only keys that identify ONE account.

    A small chain sharing a head-office number, or several stores behind one
    website, would otherwise let a single key delete every one of them. An
    ambiguous key identifies nothing, so it is dropped.
    """
    seen: dict = {}
    for key, name in pairs:
        if key is None:
            continue
        if key in seen and seen[key] != name:
            seen[key] = None           # ambiguous: burn it
        else:
            seen.setdefault(key, name)
    return {k: v for k, v in seen.items() if v is not None}


def _name_forms(name: str) -> list[str]:
    """Every string an account might reasonably be known by.

    Salesforce brackets usually hold a BRANCH — 'MORLEY(DELRAY BEACH)' — and
    _norm is right to drop them. But occasionally they hold the trading name
    behind a legal one:

        MORHAIN 417, LLC (LA BOUTIQUE ON FLAGLER)

    where the only matchable part is exactly what _norm throws away. Comparing
    against both forms costs nothing and cannot cause a false match: a branch
    suffix like 'delray beach' will not resemble a shop name.
    """
    forms = [_norm(name)]
    for inner in re.findall(r"\((.+?)\)", name or ""):
        n = _norm(inner)
        if n and n not in forms:
            forms.append(n)
    return [f for f in forms if f]


def _place_id(row) -> str | None:
    """A usable Google place_id from a row, or None.

    NOT just `row.place_id`. An all-empty place_id column survives a CSV
    round-trip as float64 NaN, and NaN is TRUTHY — so a plain `if pid:` decided
    every row was already resolved, skipped the lookup, and posted "nan" to
    Google as a place id. Empty strings arrive the same way.
    """
    v = getattr(row, "place_id", None)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = str(v).strip()
    return v or None


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
                    time.sleep(5)
                data = _get("nearbysearch", params)
                if data.get("status") not in ("OK", "ZERO_RESULTS"):
                    raise RuntimeError(f"Places: {data.get('status')} {data.get('error_message','')}")
                for r in data.get("results", []):
                    types = set(r.get("types", []))
                    if types & REJECT_TYPES and PLACE_TYPE not in types:
                        continue
                    loc = r["geometry"]["location"]
                    seen.setdefault(r["place_id"], {
                        "place_id": r["place_id"],
                        "store_name": r["name"],
                        "latitude": loc["lat"],
                        "longitude": loc["lng"],
                        "url": f"https://www.google.com/maps/search/?api=1&query={loc['lat']},{loc['lng']}&query_place_id={r['place_id']}",
                        "types": ",".join(sorted(types)),
                        "found_near": city,
                        # from the same response, no extra cost
                        "rating": r.get("rating"),
                        # a COUNT, not the review text — that needs Place Details
                        "review_count": r.get("user_ratings_total"),
                        "business_status": r.get("business_status"),
                        "vicinity": r.get("vicinity"),
                        "phone": r.get("international_phone_number"),
                        # "_raw": r,
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
        "SELECT Id, Name, Phone, Website, ShippingLatitude, ShippingLongitude, "
        "Rank__c FROM Account "
        f"WHERE SalesTerritory__c = '{safe}' "
        f"AND (Rank__c = null OR Rank__c NOT IN ('{excluded}'))"
    )
    recs = sf.query_all(q)["records"]
    df = pd.DataFrame(recs).drop(columns="attributes", errors="ignore")
    # A territory with no accounts yields an EMPTY frame with no columns at
    # all, and every caller then fails on dropna(subset=[...]) or itertuples
    # attribute access. Guaranteeing the shape means "no accounts" behaves like
    # "no matches" — which is exactly right for a territory we have not sold
    # into yet, and is the case a prospecting sweep most wants to run.
    for col in ("Id", "Name", "Phone", "Website",
                "ShippingLatitude", "ShippingLongitude", "Rank__c"):
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    return df


def classify_existing(cands: pd.DataFrame, accounts: pd.DataFrame,
                      verbose: bool = True) -> pd.DataFrame:
    """Label every candidate `existing` or `prospect`. Drops nothing.

    Returns the frame with three columns added:
        status           'existing' | 'prospect'
        matched_account  the Salesforce Name it matched, or None
        matched_by       'phone' | 'domain' | 'name+distance' | None

    LABELLING RATHER THAN DELETING is the point. "This OSM shop is already our
    customer" is expensive to work out and useful to keep: it lets a re-sweep
    skip re-deciding, it lets a human audit the matcher, and it means the map
    can draw both kinds from one table.

    Three independent rules, any one of which is a match:

      phone   ten digits equal — the strongest signal there is. Two shops never
              share a landline, and it survives a rename, a move and a bad
              geocode, all of which defeat the rule below.
      domain  same website host, platform pages excluded. Catches the shop
              trading under one name and filed in Salesforce under another.
      name    close name AND close coordinates. Neither half is sufficient
              alone: 'MORLEY(DELRAY BEACH)' vs 'Morley' defeats exact matching,
              and two different boutiques can share a mall — measured on this
              data, a Florida plaza puts unrelated storefronts 8-22 m apart, so
              proximity alone would delete real prospects.

    Phone and domain need no distance check — they identify on their own, which
    is exactly why they catch what coordinates miss. Both are indexed through
    _unique_index, so a value shared by several accounts identifies none of
    them rather than deleting all of them.

    A MISSING phone is not a DIFFERENT phone: when either side has no value the
    rule cannot fire. So these rules only ever ADD an `existing` label; a
    candidate with thin data stays a prospect.

    NOTE ON COVERAGE. This can only recognise accounts OSM actually holds.
    Measured against the Florida book, 47 of 102 accounts have no OSM clothing
    shop within 2 km at all — so `existing` here means "matched in OSM", never
    "all our stockists". The map still needs the live Salesforce list.
    """
    known = accounts.dropna(subset=["ShippingLatitude", "ShippingLongitude"])
    # One entry per NAME FORM, not per account: an account carrying a trading
    # name in brackets gets two chances to match. See _name_forms.
    pairs = [(form, r.ShippingLatitude, r.ShippingLongitude, r.Name)
             for r in known.itertuples()
             for form in _name_forms(r.Name)]
    # Indexed off `accounts`, not `known`: an account with no coordinates is
    # still perfectly identifiable by its phone or website.
    by_phone = _unique_index(
        (_phone_key(getattr(r, "Phone", None)), r.Name) for r in accounts.itertuples())
    by_domain = _unique_index(
        (_domain_key(getattr(r, "Website", None)), r.Name) for r in accounts.itertuples())

    rules, hits = [], []
    for c in cands.itertuples():
        rule = hit = None

        key = _phone_key(_first(c, "phone", "phone_local"))
        if key and key in by_phone:
            rule, hit = "phone", by_phone[key]

        if hit is None:
            key = _domain_key(_first(c, "website"))
            if key and key in by_domain:
                rule, hit = "domain", by_domain[key]

        if hit is None:
            cn = _norm(c.store_name)
            for kn, klat, klng, raw in pairs:
                if _metres(c.latitude, c.longitude, klat, klng) > SAME_PLACE_METRES:
                    continue
                if kn == cn or SequenceMatcher(None, kn, cn).ratio() >= NAME_SIMILARITY:
                    rule, hit = "name+distance", raw
                    break

        rules.append(rule)
        hits.append(hit)

    out = cands.copy()
    out["matched_by"] = rules
    out["matched_account"] = hits
    out["status"] = ["existing" if h else "prospect" for h in hits]

    if verbose:
        n_ex = sum(1 for h in hits if h)
        print(f"  already customers: {n_ex}   new prospects: {len(out) - n_ex}")
        for rule in ("phone", "domain", "name+distance"):
            rows = [(i, h) for i, (r, h) in enumerate(zip(rules, hits)) if r == rule]
            if not rows:
                continue
            print(f"    by {rule}: {len(rows)}")
            for i, h in rows[:5]:
                print(f"       {str(out.iloc[i]['store_name'])[:34]:36} = {h}")
    return out


def drop_existing(cands: pd.DataFrame, accounts: pd.DataFrame, verbose: bool = True,
                  *, with_dropped: bool = False):
    """classify_existing, then keep only the prospects.

    Thin wrapper kept because the pipeline and the notebooks call it. New code
    should prefer classify_existing and filter for itself — throwing the
    `existing` rows away loses information worth storing.
    """
    labelled = classify_existing(cands, accounts, verbose=verbose)
    is_new = labelled["status"] == "prospect"
    kept = labelled[is_new].drop(columns=["status", "matched_by", "matched_account"])
    kept = kept.reset_index(drop=True)
    if not with_dropped:
        return kept
    return kept, labelled[~is_new].reset_index(drop=True)


# Place Details fields. THE FIELD LIST SETS THE PRICE: Google bills the whole
# call at the highest tier any requested field belongs to, so one review field
# prices every call at the review tier.
#
#   website, phone, opening_hours   mid tier
#   rating, user_ratings_total,
#   reviews, price_level            TOP tier — the expensive one
#
# Website only, deliberately. It is the field that actually qualifies a shop
# (you can look at what they sell), and dropping the review fields takes every
# call down a tier. Everything else degrades rather than breaking:
#
#   state    already stamped by discover_osm from the swept state
#   address  falls back to the OSM vicinity
#   phone    falls back to the OSM phone tag
#   rating / review_count / review_text  stay None
#
# To get the richer set back for a small shortlist, override it at the call
# site rather than editing this line — it is read per request:
#
#   p.DETAIL_FIELDS = "website,formatted_address,formatted_phone_number," \
#                     "address_components,reviews,rating,user_ratings_total"
DETAIL_FIELDS = "website"


def _review_text(result: dict, limit: int = 5) -> str | None:
    """Google's reviews as one readable cell: "5* text ¦ 4* text ...".

    Flattened rather than kept as a list so it survives a CSV round-trip — a
    list of dicts in a cell comes back as an unusable string. Author names and
    photo URLs are dropped: the text is the signal, the rest is personal data
    we have no reason to carry.
    """
    reviews = (result.get("reviews") or [])[:limit]
    parts = [
        f"{r.get('rating')}* {' '.join((r.get('text') or '').split())}"
        for r in reviews
        if (r.get("text") or "").strip()
    ]
    return " ¦ ".join(parts) or None


def _state_of(result: dict) -> str | None:
    """Two-letter state from address_components — a territory can straddle one
    (FL - Jason Hilsenrad holds a Georgia account), so this is how you filter."""
    for c in result.get("address_components") or []:
        if "administrative_area_level_1" in c.get("types", []):
            return c.get("short_name")
    return None


def add_details(cands: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """Place Details: website, address, phone, state and review text.

    One billed call per candidate, so this runs AFTER dedupe. Cached by
    place_id for the session — candidates repeat between nearby origins.
    """
    sites, addrs, phones, states, reviews = [], [], [], [], []
    ratings, counts = [], []
    for row in cands.itertuples():
        pid = _place_id(row)
        # An OSM row that resolve_place_ids could not match has no place_id.
        # Skipped rather than sent to Google, which would 400 on every one.
        r = {}
        if pid:
            if pid not in _details_cache:
                d = _get("details", {"place_id": pid, "fields": DETAIL_FIELDS})
                _details_cache[pid] = d.get("result", {})
            r = _details_cache[pid]
        # Google FIRST, OSM as the fallback: Google is the fresher source, but
        # an unresolved row must keep the contact details OSM already gave it
        # rather than have them overwritten with None.
        sites.append(r.get("website") or _first(row, "website"))
        # vicinity is OSM's housenumber/street/city, the only address an
        # unresolved row has. Without it here, `address` is blank on exactly
        # the rows that most need one.
        addrs.append(r.get("formatted_address") or _first(row, "address", "vicinity"))
        phones.append(r.get("formatted_phone_number") or _first(row, "phone"))
        states.append(_state_of(r) or _first(row, "state"))
        reviews.append(_review_text(r))
        ratings.append(r.get("rating") or _first(row, "rating"))
        counts.append(r.get("user_ratings_total") or _first(row, "review_count"))
    out = cands.copy()
    out["website"] = sites
    out["address"] = addrs
    out["phone_local"] = phones
    out["state"] = states
    out["review_text"] = reviews
    out["rating"] = ratings
    out["review_count"] = counts
    if verbose:
        print(f"  with a website: {out['website'].notna().sum()} of {len(out)}"
              f"   ·  with a rating: {out['rating'].notna().sum()}"
              f"   ·  with review text: {out['review_text'].notna().sum()}")
    return out




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
    "types", "place_id", "rating", "review_count", "business_status", "vicinity",
    "phone", "phone_local", "state", "review_text",
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


# ===================================================================== OSM
# Google Places cannot enumerate a state: every search is anchored to a point
# and capped at 60 results, so a 120-hit city run is a CEILING, not a count —
# Naples saturated at exactly 120 while OSM knows 2,400+ shops state-wide.
# Overpass answers "everything inside this boundary" in one free request, so it
# is the right tool for the sweep. Google is then used only to ENRICH the
# survivors, which is the expensive part and should touch as few rows as
# possible.
# Free public service, shared by everyone — 504s and rate limits are normal,
# not a bug. Mirrors are tried in turn rather than failing the whole sweep.
OVERPASS_MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)

# shop=boutique is the strongest signal OSM has; shop=clothes is the broad net.
# Kept deliberately short: a longer alternation makes the state-wide query
# heavy enough for the free mirrors to time it out.
OSM_SHOP_TAGS = "clothes|boutique"

# National/regional chains. They satisfy every structural filter — clothing
# store, real address, often a website — and none of them will ever stock a
# small US knitwear label, so they are removed by name before anything is paid
# for. Matched on a normalised substring, so "Nike Factory Store" goes too.
CHAINS = {
    "old navy", "gap", "banana republic", "h m", "zara", "uniqlo", "forever 21",
    "nike", "adidas", "under armour", "lululemon", "athleta", "champs",
    "ross dress for less", "tj maxx", "marshalls", "burlington", "citi trends",
    "rue21", "dots", "cato", "bealls", "belk", "macy s", "dillard s", "kohl s",
    "nordstrom", "jcpenney", "target", "walmart", "sears", "century 21",
    "american eagle", "hollister", "abercrombie", "aeropostale", "pacsun",
    "urban outfitters", "anthropologie", "free people", "j crew", "loft",
    "ann taylor", "talbots", "chico s", "white house black market", "soma",
    "victoria s secret", "torrid", "lane bryant", "express", "charlotte russe",
    "windsor", "francesca s", "altar d state", "brandy melville", "akira",
    "loveshackfancy", "ba sh", "anne fontaine", "tommy bahama", "lilly pulitzer",
    "vineyard vines", "patagonia", "columbia", "north face", "levi s",
    "calvin klein", "tommy hilfiger", "polo ralph lauren", "michael kors",
    "coach", "kate spade", "guess", "bcbg", "bebe", "zumiez", "tillys",
    "buckle", "maurices", "dress barn", "justice", "children s place",
    "carter s", "gymboree", "disney store", "pele soccer", "sunglass hut",
}


def _is_chain(name: str, tags: dict | None = None) -> bool:
    """A chain, by OSM's own judgement first and our name list second.

    `brand:wikidata` means a mapper linked this shop to a known brand entity —
    authoritative, maintained by someone else, and true of 53% of Florida's
    clothing shops. The CHAINS list stays as a backstop for brands nobody has
    tagged yet, but it is the weaker signal: it caught 786 where the tags catch
    1,284, and it missed JoS. A. Bank and David's Bridal entirely.
    """
    if tags and ({"brand", "brand:wikidata"} & set(tags)):
        return True
    n = _norm(name)
    return any(c in n for c in CHAINS)


def _clothes_tokens(tags: dict) -> set[str]:
    """OSM packs several audiences into one value: 'men;women' -> {men, women}."""
    return {t for t in re.split(r"[;,]", (tags.get("clothes") or "").lower()) if t.strip()}


def _wrong_clothes(tags: dict) -> bool:
    """True when the shop states what it sells and it is not womenswear.

    ONLY fires when `clothes` is present — 65% of shops do not set it, and an
    absent tag is not evidence of anything. Silence keeps the shop; a positive
    statement of "men" or "wedding" or "hats" is what removes it.
    """
    t = _clothes_tokens(tags)
    return bool(t) and "women" not in t


def discover_osm(state: str | Sequence[str] = "FL", *, drop_chains: bool = True,
                 drop_wrong_clothes: bool = True, drop_second_hand: bool = True,
                 min_repeats: int = 3, verbose: bool = True) -> pd.DataFrame:
    """Every clothing shop OSM knows inside a US state, as prospect rows.

    Same column shape as discover(), so drop_existing / add_details /
    add_conflict / plot all work unchanged. place_id is left EMPTY — OSM has no
    Google id, and resolving one costs a Find Place call per row, so that is a
    separate opt-in step (resolve_place_ids).

    OSM coverage is volunteer-made: excellent for mapped high streets, thin for
    shops nobody has added. It is a wider net than Places, not a better one —
    which is why the two are used for different jobs.
    """
    # A territory is rarely one state ("Midwest - Aviva Landin" spans nine), so
    # accept a list. Each state is a separate Overpass request: one failing
    # mirror then costs that state, not the whole sweep, and progress is
    # visible per state rather than as one long silence.
    if not isinstance(state, str):
        states = [str(x).strip().upper() for x in state if str(x).strip()]
        if not states:
            raise ValueError("discover_osm needs at least one state code")
        if len(states) > 1:
            frames, failed = [], []
            for i, code in enumerate(states, 1):
                if verbose:
                    print(f"  [{i}/{len(states)}] {code}")
                try:
                    frames.append(
                        discover_osm(
                            code,
                            drop_chains=drop_chains,
                            drop_wrong_clothes=drop_wrong_clothes,
                            drop_second_hand=drop_second_hand,
                            # Repeated-name detection is deferred to the combined
                            # frame below: a chain with one branch per state would
                            # never reach the threshold within a single state.
                            min_repeats=0,
                            verbose=verbose,
                        )
                    )
                except Exception as exc:
                    # Overpass 504s on large states (CA is reliably slow). One
                    # state failing must not throw away the ones that worked —
                    # but a partial sweep that looked complete would be worse
                    # than an error, so the gap is reported loudly and the
                    # caller can re-run just the missing states.
                    failed.append(code)
                    print(f"    !! {code} FAILED ({type(exc).__name__}) — skipped")
            if not frames:
                raise RuntimeError(
                    f"every state failed: {', '.join(states)}. Overpass is a free "
                    "shared service; try again shortly."
                )
            out = pd.concat(frames, ignore_index=True)
            # Border shops can sit inside two state boundary queries.
            out = out.drop_duplicates(subset="osm_id").reset_index(drop=True)
            if min_repeats:
                counts: dict[str, int] = {}
                for name in out["store_name"]:
                    key = _norm(name)
                    if key:
                        counts[key] = counts.get(key, 0) + 1
                repeats = {k for k, v in counts.items() if v >= min_repeats}
                before = len(out)
                out = out[~out["store_name"].map(lambda n: _norm(n) in repeats)]
                out = out.reset_index(drop=True)
                if verbose and before != len(out):
                    print(f"  dropped {before - len(out)} more as repeated names "
                          f"across {len(states)} states -> {len(out)} candidates")
            if verbose:
                done = len(states) - len(failed)
                print(f"  TOTAL across {done}/{len(states)} states: {len(out)} candidates")
                if failed:
                    print(f"  INCOMPLETE — no data for: {', '.join(failed)}. "
                          f"Re-run discover_osm({failed!r}) and concat.")
            return out
        state = states[0]
    # Normalised HERE, not only inside the list branch: a caller passing the
    # string "ca" reached the Overpass query as US-ca (which works) and would
    # have stamped "ca" onto every row, where it matches no state filter.
    state = str(state).strip().upper()

    query = f"""
    [out:json][timeout:180];
    area["ISO3166-2"="US-{state}"][admin_level=4]->.a;
    (
      node["shop"~"{OSM_SHOP_TAGS}"](area.a);
      way["shop"~"{OSM_SHOP_TAGS}"](area.a);
    );
    out center tags;
    """
    elements, last_error = None, None
    for mirror in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(
                mirror,
                data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "wooden-ships-prospecting/1.0"},
            )
            with urllib.request.urlopen(req, timeout=300) as fh:
                elements = json.load(fh).get("elements", [])
            break
        except Exception as exc:
            last_error = exc
            if verbose:
                print(f"  {mirror.split('/')[2]} unavailable ({type(exc).__name__}) — trying the next mirror")
            time.sleep(5)
    if elements is None:
        raise RuntimeError(f"every Overpass mirror failed; last error: {last_error}")
    if not elements:
        raise RuntimeError(
            f"Overpass returned nothing for US-{state}. A regional mirror that "
            "does not hold North America will do this — check OVERPASS_MIRRORS."
        )

    rows, unnamed, chains, wrong, used = [], 0, 0, 0, 0
    for e in elements:
        tags = e.get("tags", {})
        name = (tags.get("name") or "").strip()
        if not name:
            unnamed += 1              # a shop with no name cannot be researched
            continue
        if drop_chains and _is_chain(name, tags):
            chains += 1
            continue
        if drop_second_hand and tags.get("second_hand") in ("only", "yes"):
            used += 1                 # thrift and consignment do not buy wholesale
            continue
        if drop_wrong_clothes and _wrong_clothes(tags):
            wrong += 1
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lng = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lng is None:
            continue
        city = tags.get("addr:city") or ""
        rows.append({
            "place_id": None,                       # filled by resolve_place_ids
            "osm_id": f"{e.get('type')}/{e.get('id')}",
            "store_name": name,
            "latitude": float(lat),
            "longitude": float(lng),
            "url": f"https://www.openstreetmap.org/{e.get('type')}/{e.get('id')}",
            "types": tags.get("shop", ""),
            "found_near": city,
            # Which state's sweep produced this row. Stamped here rather than
            # derived later so a multi-state run stays traceable, and so the
            # column exists even when nothing is enriched. add_details fills
            # the same column from Google when it runs, preferring Google's
            # answer and falling back to this — the two agree in practice.
            "state": state,
            "rating": None,
            "review_count": None,
            "business_status": "OPERATIONAL",
            "vicinity": ", ".join(
                v for v in (tags.get("addr:housenumber", "") + " " + tags.get("addr:street", ""), city)
                if v.strip()
            ).strip(", "),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "website": tags.get("website") or tags.get("contact:website"),
            # Free qualifying signal, straight off the tags. `womenswear` is the
            # one to sort by before spending on enrichment: a shop that STATES
            # it sells womenswear is a better bet than one that says nothing.
            "clothes": tags.get("clothes"),
            "womenswear": "women" in _clothes_tokens(tags),
            "second_hand": tags.get("second_hand"),
            "instagram": tags.get("contact:instagram") or tags.get("instagram"),
            "email": tags.get("email") or tags.get("contact:email"),
            "opening_hours": tags.get("opening_hours"),
            "postcode": tags.get("addr:postcode"),
            # The one fact this sweep knows for certain and OSM never tags:
            # the query asked for exactly this state's boundary. add_details
            # prefers Google's answer when it runs (`_state_of(r) or
            # _first(row, "state")`), so this is the free floor under it, not a
            # competitor. Without it a free run_state sweep carries no state at
            # all -- which is how 225 rows landed with the column NULL.
            "state": state,
        })
    # A name occurring this often in ONE state is a chain nobody has brand-tagged
    # — Surf Style x13, Sunelli x7, Versona x4, none of them in CHAINS. Catching
    # them by repetition needs no list to maintain and no call to Google.
    # Matched on the normalised name so "Surf Style" and "SURF STYLE #4" collapse.
    repeats = {}
    if min_repeats:
        counts: dict[str, int] = {}
        for r in rows:
            # A name made ENTIRELY of noise words ("The Boutique", "The Shop")
            # normalises to "", which would count every one of them as the same
            # chain and delete them all. Those keep their identity by being
            # excluded from the count, not by being matched.
            key = _norm(r["store_name"])
            if key:
                counts[key] = counts.get(key, 0) + 1
        repeats = {k: v for k, v in counts.items() if v >= min_repeats}
        rows = [r for r in rows if _norm(r["store_name"]) not in repeats]

    if verbose:
        print(f"  OSM returned {len(elements)} shops in {state}")
        print(f"    dropped {unnamed} unnamed, {chains} chains, {used} second-hand,"
              f" {wrong} not womenswear")
        if repeats:
            print(f"    dropped {sum(repeats.values())} more as repeated names"
                  f" ({min_repeats}+ locations): {', '.join(sorted(repeats)[:6])}...")
        print(f"    ->  {len(rows)} candidates")
        stated = sum(1 for r in rows if r["womenswear"])
        print(f"    of those, {stated} state clothes=...women... — enrich these first")
    return pd.DataFrame(rows)


def resolve_place_ids(cands: pd.DataFrame, *, max_metres: float = 300,
                      verbose: bool = True) -> pd.DataFrame:
    """Give OSM rows a Google place_id, so add_details can enrich them.

        short = df[~df.potential_conflict]
        short = p.add_details(p.resolve_place_ids(short))   # both BILLED

    OSM knows a shop exists; Google knows its website, phone, rating and
    reviews. Nothing joins the two but name and position, so this is a Find
    Place text search biased to the OSM coordinates — one billed call per row.
    Run it on a SHORTLIST, never on a whole-state sweep.

    THE MATCH IS VERIFIED BY DISTANCE. Find Place always answers with its best
    guess, so an unmapped shop happily returns the cafe next door and, left
    unchecked, that cafe's website would be presented as the prospect's. A hit
    more than `max_metres` from where OSM put the shop is discarded: an
    unresolved row costs nothing but a blank, while a wrong one is a bad
    address in a rep's hands.
    """
    if "place_id" not in cands.columns:
        cands = cands.assign(place_id=None)

    ids, hit, miss, far = [], 0, 0, 0
    for c in cands.itertuples():
        known = _place_id(c)
        if known:
            ids.append(known)                  # already resolved; do not re-bill
            continue
        query = " ".join(str(v) for v in (c.store_name, _first(c, "vicinity")) if v)
        try:
            d = _get("findplacefromtext", {
                "input": query,
                "inputtype": "textquery",
                "fields": "place_id,geometry/location",
                "locationbias": f"circle:2000@{c.latitude},{c.longitude}",
            })
            best = (d.get("candidates") or [None])[0]
        except Exception as exc:              # never let one lookup kill the run
            print(f"    find place failed for {c.store_name}: {exc}")
            best = None
        if not best:
            ids.append(None); miss += 1; continue
        loc = (best.get("geometry") or {}).get("location") or {}
        if loc and _metres(c.latitude, c.longitude, loc["lat"], loc["lng"]) > max_metres:
            ids.append(None); far += 1; continue
        ids.append(best.get("place_id")); hit += 1

    out = cands.copy()
    out["place_id"] = ids
    if verbose:
        print(f"  resolved {hit} of {len(out)}   ·  no match {miss}"
              f"   ·  rejected as too far {far}")
    return out


def add_conflict_fast(cands: pd.DataFrame, accounts: pd.DataFrame,
                      max_miles: float = 10.0, verbose: bool = True) -> pd.DataFrame:
    """Straight-line nearest-stockist distance. NO API calls, so it scales.

    add_conflict() is the authority — it uses the app's own rule and real drive
    times — but it costs a Distance Matrix lookup per candidate, which is not
    affordable across a whole state. Use this to shortlist, then run the real
    check on what survives.

    10 miles is the straight-line stand-in the app itself documents for a
    20-minute drive (app/geo/conflict.py: 20 min ~ 10 mi at 30 mph).
    """
    known = accounts.dropna(subset=["ShippingLatitude", "ShippingLongitude"])
    pts = [(r.Name, r.ShippingLatitude, r.ShippingLongitude) for r in known.itertuples()]

    nearest, miles = [], []
    for c in cands.itertuples():
        best_name, best_m = None, float("inf")
        for name, klat, klng in pts:
            d = _metres(c.latitude, c.longitude, klat, klng)
            if d < best_m:
                best_name, best_m = name, d
        nearest.append(best_name)
        miles.append(round(best_m / 1609.34, 1) if best_m < float("inf") else None)

    out = cands.copy()
    out["nearest_stockist"] = nearest
    out["distance_miles"] = miles
    out["potential_conflict"] = [m is not None and m < max_miles for m in miles]
    out["drive_minutes"] = None          # straight-line pass; no drive time yet
    if verbose:
        flagged = sum(1 for m in miles if m is not None and m < max_miles)
        print(f"  within {max_miles} mi of a stockist: {flagged} of {len(out)}"
              f"   (straight-line — run add_conflict on the shortlist for drive time)")
    return out


def run_state(
    sf,
    territory: str | Mapping[str, Sequence[str]],
    state: str | Sequence[str] | None = None,
) -> pd.DataFrame:
    """Whole-territory sweep: OSM -> label existing -> straight-line conflict.

    Deliberately free of billed calls so it can be run over and over while the
    filters are tuned. Enrich afterwards, on a shortlist:

        df = p.run_state(sf, "FL - Jason Hilsenrad")
        short = df[~df.potential_conflict].head(50)
        short = p.add_details(p.resolve_place_ids(short))   # billed

    `territory` may also be a MAPPING of {territory: [state codes]}, in which
    case every entry is swept and the results concatenated:

        df = p.run_state(sf, {"CA/HI - Rande Cohen": ["CA", "HI"],
                              "FL - Jason Hilsenrad": ["FL"]})

    That form exists because the states a territory covers are sometimes known
    (or overridden) locally, and pasting a dict beats eleven separate calls
    that each have to be concatenated by hand. Every row carries `territory`
    and `state`, so a combined frame stays traceable to where each shop came
    from. One territory failing is reported and skipped rather than losing the
    others — same rule as a failing state inside discover_osm.

    `state` is optional for the single-territory form and normally omitted: the
    REGION sheet already knows which states a territory covers, and a territory
    is rarely one of them — "Midwest - Aviva Landin" is nine. Deriving it means
    a sweep cannot quietly cover a fraction of the book because someone passed
    the label's prefix. Pass it explicitly only to sweep something narrower.
    """
    if isinstance(territory, Mapping):
        if state is not None:
            raise ValueError(
                "Pass either a {territory: [states]} mapping or a single "
                "territory with state=, not both."
            )
        frames, failed = [], []
        for i, (name, states) in enumerate(territory.items(), 1):
            print(f"\n=== [{i}/{len(territory)}] {name} ===")
            try:
                part = run_state(sf, name, states)
            except Exception as exc:
                failed.append(name)
                print(f"  !! {name} FAILED ({type(exc).__name__}: {exc}) — skipped")
                continue
            if not part.empty:
                part = part.copy()
                part["territory"] = name
                frames.append(part)
        if not frames:
            raise RuntimeError(
                f"every territory failed or returned nothing: {', '.join(territory)}"
            )
        out = pd.concat(frames, ignore_index=True)
        # A shop on a shared border can be swept by two territories.
        out = out.drop_duplicates(subset="osm_id").reset_index(drop=True)
        print(f"\n=== TOTAL {len(out)} prospects across "
              f"{len(territory) - len(failed)}/{len(territory)} territories ===")
        if failed:
            print(f"  INCOMPLETE — no data for: {', '.join(failed)}")
        return out

    if state is None:
        # Imported HERE, not at module scope. app.sheets pulls in
        # google-api-python-client, and requiring that just to import this
        # module broke the notebook — where the sweep is normally driven and
        # where nothing else needs Sheets. Only deriving the state list needs
        # it, so only that path pays for it.
        from app.sheets import client as sheets_client

        state = sheets_client.states_for_territory(territory)
        if not state:
            raise ValueError(
                f"No states mapped to {territory!r} in the REGION sheet — pass "
                "state= explicitly, or add the territory to the sheet."
            )
        print(f"   {territory} covers {len(state)} state(s): {', '.join(state)}")

    print(f"1. OSM sweep of {state}")
    cands = discover_osm(state)
    print(f"2. dedupe against active accounts in {territory!r}")
    accounts = existing_accounts(sf, territory)
    cands = drop_existing(cands, accounts)
    if cands.empty:
        print("   nothing left after dedupe")
        return cands
    print("3. nearest stockist (straight-line)")
    out = add_conflict_fast(cands, accounts).sort_values(
        ["potential_conflict", "store_name"]
    ).reset_index(drop=True)
    # Carried on every row so a frame stays readable after several sweeps are
    # concatenated, and so the loader has the value the prospects table wants.
    out["territory"] = territory
    return out
