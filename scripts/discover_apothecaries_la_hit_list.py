#!/usr/bin/env python3
"""
Discover apothecary-like stores via Google Places Nearby Search (multi-region),
pre-filter obvious pharmacies / cannabis retail, dedupe against the live Hit List, then
append new rows with Status=Research for scripts/hit_list_research_photo_review.py (CI).

**Regions** are defined below (search centroids + bounding box + Notes label). To add a
new metro: copy an entry in REGIONS, tune centers (overlap ~50 km disks), set lat/lng
bounds to drop bleed from adjacent states or wrong metro, document in HIT_LIST_CREDENTIALS.md.

Requires:
  - GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY in market_research/.env (server/IP key)
  - google_credentials.json with Editor access to the Hit List spreadsheet

Usage:
  cd market_research
  python3 scripts/discover_apothecaries_la_hit_list.py --region la --dry-run
  python3 scripts/discover_apothecaries_la_hit_list.py --region sf_bay --max-new 120
  python3 scripts/discover_apothecaries_i5_pipeline.py --max-new 300
  python3 scripts/discover_apothecaries_la_hit_list.py --region ca_hwy_101 --dry-run
  python3 scripts/discover_apothecaries_la_hit_list.py --region ca_i280 --max-new 120

Nearby Search uses multiple centroids (max radius 50 km per Google); results are deduped
by place_id. Rows outside the region bounding box or wrong state are skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gspread
import requests
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Column order must match Hit List tab (see HIT_LIST_CREDENTIALS.md, append_to_hit_list.py)
HIT_LIST_OPENING_HOUR_COLS: tuple[str, ...] = (
    "Monday Open",
    "Monday Close",
    "Tuesday Open",
    "Tuesday Close",
    "Wednesday Open",
    "Wednesday Close",
    "Thursday Open",
    "Thursday Close",
    "Friday Open",
    "Friday Close",
    "Saturday Open",
    "Saturday Close",
    "Sunday Open",
    "Sunday Close",
)

# Google Place Details ``business_status`` → Hit List cell (empty = operational / unknown).
GOOGLE_LISTING_COL = "Google listing"


def google_listing_from_business_status(status: str | None) -> str:
    s = (status or "").strip().upper()
    if s == "CLOSED_PERMANENTLY":
        return "Closed"
    if s == "CLOSED_TEMPORARILY":
        return "Temporarily closed"
    return ""


HIT_LIST_COLS = [
    "Shop Name",
    "Status",
    "Priority",
    "Address",
    "City",
    "State",
    "Shop Type",
    "Phone",
    "Cell Phone",
    "Website",
    "Email",
    "Instagram",
    "Notes",
    "Contact Date",
    "Contact Method",
    "Follow Up Date",
    "Contact Person",
    "Owner Name",
    "Referral",
    "Product Interest",
    "Follow Up Event Link",
    "Visit Date",
    "Outcome",
    "Sales Process Notes",
    "Latitude",
    "Longitude",
    "Status Updated By",
    "Status Updated Date",
    "Instagram Follow Count",
    "Store Key",
    "Contact Form URL",
    *HIT_LIST_OPENING_HOUR_COLS,
    GOOGLE_LISTING_COL,
]

NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"


def find_place_from_text(
    key: str,
    query: str,
    lat: float | None,
    lng: float | None,
    radius_m: float = 50000.0,
) -> dict[str, Any]:
    """
    Find Place from Text (legacy Places API). Prefer ``locationbias`` when lat/lng are known.
    Returns the full JSON (status, candidates, …).
    """
    params: dict[str, Any] = {
        "input": (query or "").strip(),
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,business_status",
        "key": key,
    }
    if lat is not None and lng is not None:
        params["locationbias"] = f"circle:{int(radius_m)}@{lat},{lng}"
    r = requests.get(FIND_PLACE_URL, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


@dataclass(frozen=True)
class RegionConfig:
    """One metro: Nearby centroids, bbox filter, spreadsheet Notes tag."""

    key: str
    notes_label: str
    centers: tuple[tuple[float, float, int, str], ...]
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float
    fallback_city: str
    required_state: str = "CA"
    # When set (e.g. I-5), accept any of these state codes after Place Details.
    allowed_states: frozenset[str] | None = None


# Centroids: (lat, lng, radius_m, label). Radius capped at 50_000 per Places API.
REGIONS: dict[str, RegionConfig] = {
    "la": RegionConfig(
        key="la",
        notes_label="Los Angeles metro",
        centers=(
            (34.052235, -118.243683, 50000, "Downtown LA"),
            (34.019481, -118.491227, 50000, "Santa Monica"),
            (34.147785, -118.144516, 50000, "Pasadena"),
            (33.770050, -118.193739, 50000, "Long Beach"),
            (34.180840, -118.308967, 50000, "Burbank/Glendale"),
            (33.835849, -118.340628, 50000, "Torrance"),
            (34.068621, -117.937035, 45000, "West Covina"),
            (34.278289, -118.745441, 45000, "Simi Valley / NW valley"),
        ),
        min_lat=33.35,
        max_lat=35.05,
        min_lng=-119.05,
        max_lng=-117.20,
        fallback_city="Los Angeles",
    ),
    "sf_bay": RegionConfig(
        key="sf_bay",
        notes_label="San Francisco Bay Area",
        centers=(
            (37.7749, -122.4194, 50000, "San Francisco"),
            (37.8044, -122.2712, 50000, "Oakland"),
            (37.3382, -121.8863, 50000, "San Jose"),
            (37.8716, -122.2728, 45000, "Berkeley"),
            (37.4852, -122.2364, 45000, "Redwood City"),
            (37.9722, -122.0016, 45000, "Concord"),
            (38.4404, -122.7144, 40000, "Santa Rosa"),
            (38.1041, -122.2566, 40000, "Vallejo"),
        ),
        min_lat=36.90,
        max_lat=38.55,
        min_lng=-122.75,
        max_lng=-121.35,
        fallback_city="San Francisco",
    ),
    # West Coast I-5 spine: overlapping 50 km searches from San Diego to Everett, WA.
    # Bounding box trims inland bleed; states CA, OR, WA only (allowed_states).
    "i5_corridor": RegionConfig(
        key="i5_corridor",
        notes_label="I-5 corridor (CA–OR–WA)",
        centers=(
            (32.7157, -117.1611, 50000, "San Diego"),
            (33.1959, -117.3795, 45000, "Oceanside / N County"),
            (33.8366, -117.9143, 50000, "Orange County (Anaheim–Santa Ana)"),
            (34.0522, -118.2437, 50000, "Los Angeles (I-5 link)"),
            (35.3733, -119.0187, 50000, "Bakersfield"),
            (37.9577, -121.2908, 50000, "Stockton"),
            (38.5816, -121.4944, 50000, "Sacramento"),
            (40.5865, -122.3917, 45000, "Redding"),
            (42.3265, -122.8756, 45000, "Medford"),
            (44.0521, -123.0868, 50000, "Eugene"),
            (44.9429, -123.0351, 45000, "Salem"),
            (45.5152, -122.6784, 50000, "Portland OR"),
            (45.6272, -122.6734, 35000, "Vancouver WA"),
            (47.0379, -122.9007, 45000, "Olympia"),
            (47.2529, -122.4443, 45000, "Tacoma"),
            (47.6062, -122.3321, 50000, "Seattle"),
            (47.9790, -122.2021, 40000, "Everett"),
        ),
        min_lat=32.42,
        max_lat=49.25,
        min_lng=-124.30,
        max_lng=-116.35,
        fallback_city="San Diego",
        required_state="CA",
        allowed_states=frozenset({"CA", "OR", "WA"}),
    ),
    # San Diego through Portland OR only (no Washington stops); CA + OR states.
    "i5_sd_portland": RegionConfig(
        key="i5_sd_portland",
        notes_label="I-5 San Diego–Portland (CA–OR)",
        centers=(
            (32.7157, -117.1611, 50000, "San Diego"),
            (33.1959, -117.3795, 45000, "Oceanside / N County"),
            (33.8366, -117.9143, 50000, "Orange County (Anaheim–Santa Ana)"),
            (34.0522, -118.2437, 50000, "Los Angeles (I-5 link)"),
            (35.3733, -119.0187, 50000, "Bakersfield"),
            (37.9577, -121.2908, 50000, "Stockton"),
            (38.5816, -121.4944, 50000, "Sacramento"),
            (40.5865, -122.3917, 45000, "Redding"),
            (42.3265, -122.8756, 45000, "Medford"),
            (44.0521, -123.0868, 50000, "Eugene"),
            (44.9429, -123.0351, 45000, "Salem"),
            (45.5152, -122.6784, 50000, "Portland OR"),
        ),
        min_lat=32.42,
        max_lat=45.62,
        min_lng=-124.30,
        max_lng=-116.35,
        fallback_city="San Diego",
        required_state="CA",
        allowed_states=frozenset({"CA", "OR"}),
    ),
    # California US-101: coastal / Central Coast / Bay / North Coast (CA only).
    "ca_hwy_101": RegionConfig(
        key="ca_hwy_101",
        notes_label="California Hwy 101 corridor",
        centers=(
            (32.7157, -117.1611, 45000, "San Diego (101)"),
            (33.1959, -117.3795, 45000, "North County coastal"),
            (33.7033, -117.9816, 45000, "Orange County 101"),
            (34.2085, -118.4486, 50000, "Los Angeles 101 (Valley/Ventura gateway)"),
            (34.2783, -119.2931, 50000, "Ventura / Oxnard"),
            (34.4208, -119.6982, 50000, "Santa Barbara"),
            (35.2828, -120.6596, 45000, "San Luis Obispo"),
            (35.6268, -120.6896, 45000, "Paso Robles / Templeton 101"),
            (36.6777, -121.6555, 45000, "Salinas"),
            (36.6002, -121.8947, 40000, "Monterey Peninsula"),
            (36.9741, -122.0308, 45000, "Santa Cruz (101/17)"),
            (36.9108, -121.7569, 45000, "Watsonville / Pajaro"),
            (37.3382, -121.8863, 50000, "San Jose 101"),
            (37.7749, -122.4184, 50000, "San Francisco 101"),
            (37.9735, -122.5311, 45000, "San Rafael / Marin 101"),
            (38.2324, -122.6367, 45000, "Petaluma"),
            (38.4404, -122.7144, 45000, "Santa Rosa"),
            (39.1502, -123.2078, 45000, "Ukiah"),
            (39.4096, -123.3556, 40000, "Willits"),
            (40.8021, -124.1637, 45000, "Eureka / Humboldt"),
            (41.7558, -124.2026, 40000, "Crescent City"),
        ),
        min_lat=32.45,
        max_lat=42.10,
        min_lng=-124.45,
        max_lng=-117.45,
        fallback_city="Los Angeles",
    ),
    # California I-280: San Francisco south through the Peninsula to San Jose.
    "ca_i280": RegionConfig(
        key="ca_i280",
        notes_label="California I-280 (SF Peninsula)",
        centers=(
            (37.7211, -122.4754, 40000, "San Francisco (280 south)"),
            (37.6879, -122.4703, 35000, "Daly City"),
            (37.6547, -122.4077, 35000, "South San Francisco"),
            (37.6305, -122.4111, 35000, "San Bruno"),
            (37.5934, -122.3872, 35000, "Millbrae / Burlingame"),
            (37.5630, -122.3255, 35000, "San Mateo"),
            (37.5201, -122.2755, 35000, "Belmont / San Carlos"),
            (37.4852, -122.2364, 35000, "Redwood City"),
            (37.4419, -122.1430, 35000, "Palo Alto"),
            (37.3858, -122.0880, 35000, "Mountain View / Los Altos"),
            (37.3230, -122.0527, 40000, "Cupertino / Saratoga gap"),
            (37.3163, -121.9363, 45000, "San Jose (280 terminus)"),
        ),
        min_lat=37.18,
        max_lat=37.88,
        min_lng=-122.58,
        max_lng=-121.82,
        fallback_city="San Francisco",
    ),
}


def region_from_arg(name: str) -> RegionConfig:
    k = (name or "").strip().lower()
    if k not in REGIONS:
        raise SystemExit(
            f"Unknown region {name!r}. Use one of: {', '.join(sorted(REGIONS.keys()))}"
        )
    return REGIONS[k]


# Types that are almost never our target apothecary row
EXCLUDE_TYPES = frozenset(
    {
        "pharmacy",
        "drugstore",
        "hospital",
        "doctor",
        "dentist",
        "veterinary_care",
        "physiotherapist",
        # “Apothecary” keyword often matches mall / dept-store beauty counters.
        "department_store",
        "shopping_mall",
        # Drink venues: keyword “apothecary” often matches themed cocktail bars (e.g. cocktail bar
        # inside a bar collective). Legacy Places types — see Google legacy Table 1.
        "bar",
        "night_club",
        "brewery",
        "liquor_store",
        # Newer Places type strings sometimes appear alongside legacy types in Details.
        "cocktail_bar",
        "wine_bar",
        "sports_bar",
        "lounge_bar",
        "irish_pub",
        "hookah_bar",
        "beer_garden",
        "brewpub",
        "gastropub",
    }
)

# Name / vicinity hints for drink-first venues when Google types are generic (establishment only).
BAR_NAME_FRAGMENTS = (
    "cocktail bar",
    "cocktail lounge",
    "craft cocktail",
    " speakeasy",
    "speakeasy ",
    " tiki bar",
    " rum bar",
    " gin bar",
    " whiskey bar",
    " whisky bar",
    "wine bar",
    "brewpub",
    " taproom",
    "beer garden",
)

# Name / vicinity heuristics (case-insensitive)
PHARMACY_NAME_FRAGMENTS = (
    "cvs ",
    "cvs#",
    "walgreens",
    "rite aid",
    "duane reade",
    "walmart pharmacy",
    "costco pharmacy",
    "target pharmacy",
    "savon",
    "longs drugs",
    "pharmacy #",
    " pharmacy",
    " rx ",
    " rite ",
    "wells fargo",
)

CANNABIS_FRAGMENTS = (
    "dispensar",
    "cannabis ",
    "cannabis-",
    "marijuana",
    "weed ",
    "mary jane",
    " thc ",
    "cbd dispens",
    "retail cannabis",
    "420 ",
    " 420",
    "kush ",
    "pre-roll",
    " flower co",
    "stiiizy",
    "leafly",
    "med men",
    "canna ",
    "canna-",
)

CHAIN_VITAMIN_FRAGMENTS = (
    "gnc ",
    "vitamin shoppe",
    "the vitamin shoppe",
)

# High-end / mass cosmetics retail often masquerades as “apothecary” in keyword search.
COSMETICS_RETAIL_FRAGMENTS = (
    "sephora",
    "ulta beauty",
    "ulta ",
    "bloomingdale",
    "nordstrom",
    "space nk",
    "saks fifth",
    "neiman marcus",
    "blue mercury",
    "bluemercury",
)


def load_dotenv_repo() -> None:
    env_path = REPO / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def maps_api_key() -> str:
    load_dotenv_repo()
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    k = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not k:
        raise SystemExit("Set GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) in market_research/.env")
    return k


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def slug_segment(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "x"


def normalize_street_line(street: str) -> str:
    """Collapse common abbreviations and junk so the same storefront gets one Store Key."""
    s = (street or "").strip().lower()
    s = re.sub(r"\s*#.*$", "", s)
    s = re.sub(r"\s*,\s*(suite|ste|unit|apt|#)\b.*$", "", s, flags=re.I)
    pairs = (
        (r"\bst\b\.?", " street"),
        (r"\bstr\b\.?", " street"),
        (r"\bave\b\.?", " avenue"),
        (r"\bav\b\.?", " avenue"),
        (r"\bblvd\b\.?", " boulevard"),
        (r"\bdr\b\.?", " drive"),
        (r"\brd\b\.?", " road"),
        (r"\brte\b\.?", " route"),
        (r"\bhwy\b\.?", " highway"),
        (r"\bln\b\.?", " lane"),
        (r"\bct\b\.?", " court"),
        (r"\bpl\b\.?", " place"),
        (r"\bpkwy\b\.?", " parkway"),
        (r"\bway\b\.?", " way"),
    )
    for pat, rep in pairs:
        s = re.sub(pat, rep, s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compute_store_key(name: str, street: str, city: str, state: str) -> str:
    st = normalize_street_line(street)
    return (
        f"{slug_segment(name)}__{slug_segment(st)}__"
        f"{slug_segment(city)}__{slug_segment(state)}"
    )


def compute_store_key_legacy(name: str, street: str, city: str, state: str) -> str:
    """Pre-normalization key style (raw address slug only); indexed for older Hit List rows."""
    return (
        f"{slug_segment(name)}__{slug_segment(street)}__"
        f"{slug_segment(city)}__{slug_segment(state)}"
    )


def geo_name_fingerprint(
    name: str, lat: float | None, lng: float | None
) -> tuple[str, str, str] | None:
    """Same shop often re-appears when address formatting or city parsing differs."""
    if not (name or "").strip() or lat is None or lng is None:
        return None
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    return (slug_segment(name), f"{la:.4f}", f"{ln:.4f}")


def name_address_fingerprint(name: str, street: str) -> tuple[str, str] | None:
    """Dedupe key for Shop Name (A) + Address (D) only — normalized like Store Key street line."""
    n = (name or "").strip()
    if not n:
        return None
    st = normalize_street_line(street)
    if not st:
        return None
    return (slug_segment(n), st)


def _norm_haystack(name: str, vicinity: str = "") -> str:
    return f"{name} {vicinity}".lower()


def should_exclude(name: str, types: list[str], vicinity: str = "") -> tuple[bool, str]:
    tset = {x.lower() for x in (types or [])}
    if EXCLUDE_TYPES & tset:
        return True, "google_type_excluded"

    hay = _norm_haystack(name, vicinity)
    for frag in PHARMACY_NAME_FRAGMENTS:
        if frag in hay:
            return True, f"pharmacy_name:{frag.strip()}"
    for frag in CANNABIS_FRAGMENTS:
        if frag in hay:
            return True, f"cannabis:{frag.strip()}"
    for frag in CHAIN_VITAMIN_FRAGMENTS:
        if frag in hay:
            return True, f"chain:{frag.strip()}"
    for frag in COSMETICS_RETAIL_FRAGMENTS:
        if frag in hay:
            return True, f"cosmetics:{frag.strip()}"
    for frag in BAR_NAME_FRAGMENTS:
        if frag in hay:
            return True, f"bar_name:{frag.strip()}"

    return False, ""


def nearby_page(
    key: str,
    lat: float,
    lng: float,
    radius: int,
    keyword: str,
    pagetoken: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "location": f"{lat},{lng}",
        "radius": str(radius),
        "keyword": keyword,
        "key": key,
    }
    if pagetoken:
        params["pagetoken"] = pagetoken
    r = requests.get(NEARBY_URL, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


def collect_nearby_for_center(
    key: str,
    lat: float,
    lng: float,
    radius: int,
    keyword: str,
    label: str,
    sleep_s: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pagetoken: str | None = None
    page = 0
    while True:
        page += 1
        data = nearby_page(key, lat, lng, radius, keyword, pagetoken)
        st = data.get("status")
        if st not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(f"Nearby search failed ({label} p{page}): {data}")
        for res in data.get("results") or []:
            out.append({**res, "_search_label": label})
        pagetoken = data.get("next_page_token")
        if not pagetoken:
            break
        time.sleep(max(2.0, sleep_s))
    return out


def place_details(key: str, place_id: str) -> dict[str, Any]:
    fields = (
        "place_id,name,formatted_address,formatted_phone_number,website,geometry,"
        "types,address_component,business_status,url,opening_hours"
    )
    r = requests.get(
        DETAILS_URL,
        params={"place_id": place_id, "fields": fields, "key": key},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()


# Google weekday on periods: 0 = Sunday .. 6 = Saturday.
_GOOGLE_DAY_TO_PAIR_START: dict[int, int] = {
    0: 12,
    1: 0,
    2: 2,
    3: 4,
    4: 6,
    5: 8,
    6: 10,
}


def opening_hours_week_grid_from_place_result(res: dict[str, Any]) -> dict[str, str]:
    """
    Build the 14 Hit List hour cells from legacy Place Details ``opening_hours.periods``.
    Multiple same-day segments: earliest open and latest close (lunch gaps not modeled).
    """
    out: dict[str, str] = {c: "" for c in HIT_LIST_OPENING_HOUR_COLS}
    oh = res.get("opening_hours") or {}
    periods = oh.get("periods") or []
    if not periods:
        return out

    # Per Google day index: list of (open_min, close_min) where close may be >1440 if overnight.
    intervals: dict[int, list[tuple[int, int]]] = {d: [] for d in range(7)}

    def parse_day_time(day: Any, tim: str | None) -> tuple[int, int] | None:
        try:
            d = int(day)
        except (TypeError, ValueError):
            return None
        if d < 0 or d > 6:
            return None
        s = (tim or "").strip()
        if not s.isdigit():
            return None
        if len(s) == 3:
            s = s.zfill(4)
        if len(s) != 4:
            return None
        mins = int(s[:2]) * 60 + int(s[2:])
        return d, mins

    for p in periods:
        o = p.get("open") or {}
        c = p.get("close") or {}
        op = parse_day_time(o.get("day"), o.get("time"))
        if not op:
            continue
        open_day, open_m = op
        cp = parse_day_time(c.get("day"), c.get("time"))
        if not cp:
            # Open 24h (no close) — treat as full day for that weekday.
            intervals[open_day].append((0, 24 * 60))
            continue
        close_day, close_m = cp
        if close_day == open_day:
            end_m = close_m if close_m > open_m else close_m + 24 * 60
            intervals[open_day].append((open_m, end_m))
        else:
            # Overnight (e.g. Mon 22:00 → Tue 02:00): measure from open day's midnight.
            span = (24 * 60 - open_m) + close_m
            end_m = open_m + span
            intervals[open_day].append((open_m, end_m))

    for d, segs in intervals.items():
        if not segs:
            continue
        start = min(s for s, _ in segs)
        end = max(e for _, e in segs)
        pair0 = _GOOGLE_DAY_TO_PAIR_START.get(d)
        if pair0 is None:
            continue
        open_col = HIT_LIST_OPENING_HOUR_COLS[pair0]
        close_col = HIT_LIST_OPENING_HOUR_COLS[pair0 + 1]
        out[open_col] = f"{start // 60:02d}:{start % 60:02d}"
        end_norm = end % (24 * 60)
        out[close_col] = f"{end_norm // 60:02d}:{end_norm % 60:02d}"

    return out


def parse_address_components(comps: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in comps or []:
        types = c.get("types") or []
        long_name = (c.get("long_name") or "").strip()
        short_name = (c.get("short_name") or "").strip()
        if "street_number" in types:
            out["street_number"] = long_name
        if "route" in types:
            out["route"] = long_name
        if "locality" in types:
            out["city"] = long_name
        if "sublocality" in types or "neighborhood" in types:
            if "city" not in out and long_name:
                out["_neighborhood"] = long_name
        if "administrative_area_level_1" in types:
            out["state"] = short_name or long_name
        if "postal_code" in types:
            out["zip"] = long_name
    street = " ".join(
        p for p in (out.get("street_number", ""), out.get("route", "")) if p
    ).strip()
    out["street_line"] = street
    return out


def extract_existing_for_dedupe(
    ws: gspread.Worksheet,
) -> tuple[set[str], set[str], set[tuple[str, str, str]], set[tuple[str, str]]]:
    """Store keys, place_ids in Notes, name+geo fingerprints, and name+Address (normalized) keys."""
    rows = ws.get_all_values()
    if len(rows) < 2:
        return set(), set(), set(), set()
    header = rows[0]

    def col(name: str) -> int:
        try:
            return header.index(name)
        except ValueError:
            return -1

    sk_i = col("Store Key")
    name_i = col("Shop Name")
    addr_i = col("Address")
    city_i = col("City")
    state_i = col("State")
    notes_i = col("Notes")
    lat_i = col("Latitude")
    lng_i = col("Longitude")

    keys: set[str] = set()
    place_ids: set[str] = set()
    geo_name: set[tuple[str, str, str]] = set()
    name_addr: set[tuple[str, str]] = set()

    pid_re = re.compile(
        r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})",
    )

    for row in rows[1:]:
        if sk_i >= 0 and sk_i < len(row):
            k = row[sk_i].strip()
            if k:
                keys.add(k)

        name = row[name_i].strip() if name_i >= 0 and name_i < len(row) else ""
        street = row[addr_i].strip() if addr_i >= 0 and addr_i < len(row) else ""
        city = row[city_i].strip() if city_i >= 0 and city_i < len(row) else ""
        state = row[state_i].strip() if state_i >= 0 and state_i < len(row) else ""
        if name:
            keys.add(compute_store_key(name, street, city, state))
            keys.add(compute_store_key_legacy(name, street, city, state))

        if notes_i >= 0 and notes_i < len(row):
            notes = row[notes_i] or ""
            for m in pid_re.finditer(notes):
                place_ids.add(m.group(1).strip())

        lat_s = row[lat_i].strip() if lat_i >= 0 and lat_i < len(row) else ""
        lng_s = row[lng_i].strip() if lng_i >= 0 and lng_i < len(row) else ""
        try:
            lat_f = float(lat_s) if lat_s else None
            lng_f = float(lng_s) if lng_s else None
        except ValueError:
            lat_f, lng_f = None, None
        fp = geo_name_fingerprint(name, lat_f, lng_f) if lat_f is not None and lng_f is not None else None
        if fp:
            geo_name.add(fp)

        na = name_address_fingerprint(name, street)
        if na:
            name_addr.add(na)

    return keys, place_ids, geo_name, name_addr


def row_dict_for_append(
    name: str,
    street: str,
    city: str,
    state: str,
    lat: float,
    lng: float,
    phone: str,
    website: str,
    shop_type: str,
    place_id: str,
    region_notes_label: str,
    opening_hours_row: Mapping[str, str] | None = None,
    google_listing: str = "",
) -> dict[str, str]:
    notes = (
        f"Auto-discovered (Google Places Nearby, {region_notes_label}). place_id: {place_id}. "
        "Pre-filtered pharmacies/cannabis chains; confirm shop type before outreach."
    )
    sk = compute_store_key(name, street, city, state)
    rd: dict[str, str] = {
        "Shop Name": name,
        "Status": "Research",
        "Priority": "Low",
        "Address": street,
        "City": city,
        "State": state,
        "Shop Type": shop_type,
        "Phone": phone,
        "Cell Phone": "",
        "Website": website or "",
        "Email": "",
        "Instagram": "",
        "Notes": notes,
        "Contact Date": "",
        "Contact Method": "",
        "Follow Up Date": "",
        "Contact Person": "",
        "Owner Name": "",
        "Referral": "",
        "Product Interest": "",
        "Follow Up Event Link": "",
        "Visit Date": "",
        "Outcome": "",
        "Sales Process Notes": "",
        "Latitude": str(lat),
        "Longitude": str(lng),
        "Status Updated By": "",
        "Status Updated Date": "",
        "Instagram Follow Count": "",
        "Store Key": sk,
        "Contact Form URL": "",
    }
    for c in HIT_LIST_OPENING_HOUR_COLS:
        rd[c] = ""
    if opening_hours_row:
        for c in HIT_LIST_OPENING_HOUR_COLS:
            v = (opening_hours_row.get(c) or "").strip()
            if v:
                rd[c] = v
    rd[GOOGLE_LISTING_COL] = (google_listing or "").strip()
    return rd


def main() -> None:
    p = argparse.ArgumentParser(
        description="Discover apothecaries by region via Places, filter, append Hit List (Research)."
    )
    p.add_argument(
        "--region",
        default="la",
        metavar="KEY",
        help=f"Region preset: {', '.join(sorted(REGIONS.keys()))} (default: la).",
    )
    p.add_argument("--dry-run", action="store_true", help="Do not write the sheet; print plan.")
    p.add_argument(
        "--keyword",
        default="apothecary",
        help='Nearby Search keyword (default: "apothecary").',
    )
    p.add_argument(
        "--max-new",
        type=int,
        default=200,
        help="Max rows to append this run (default 200).",
    )
    p.add_argument(
        "--shop-type",
        default="Metaphysical/Spiritual",
        help='Shop Type cell for new rows (default "Metaphysical/Spiritual").',
    )
    p.add_argument(
        "--sleep-details",
        type=float,
        default=0.08,
        help="Seconds between Place Details calls (default 0.08).",
    )
    args = p.parse_args()
    region = region_from_arg(args.region)

    key = maps_api_key()
    seen_place_ids: set[str] = set()
    raw_results: list[dict[str, Any]] = []

    print(f"Region: {region.key} ({region.notes_label})", flush=True)
    for lat, lng, radius, label in region.centers:
        chunk = collect_nearby_for_center(
            key, lat, lng, radius, args.keyword, label, sleep_s=2.0
        )
        raw_results.extend(chunk)
        print(f"[nearby] {label}: +{len(chunk)} raw (running total {len(raw_results)})", flush=True)

    for r in raw_results:
        pid = r.get("place_id")
        if pid:
            seen_place_ids.add(pid)

    print(f"Unique place_id from Nearby: {len(seen_place_ids)}", flush=True)

    nearby_meta: dict[str, tuple[str, list[str], str]] = {}
    for r in raw_results:
        pid = r.get("place_id")
        if not pid:
            continue
        name = (r.get("name") or "").strip()
        types = list(r.get("types") or [])
        vic = (r.get("vicinity") or "").strip()
        if pid not in nearby_meta:
            nearby_meta[pid] = (name, types, vic)

    gc = gspread_client() if not args.dry_run else None
    existing_keys: set[str] = set()
    existing_pids: set[str] = set()
    existing_geo_name: set[tuple[str, str, str]] = set()
    existing_name_addr: set[tuple[str, str]] = set()
    if gc is not None:
        ws0 = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
        existing_keys, existing_pids, existing_geo_name, existing_name_addr = extract_existing_for_dedupe(ws0)
        print(
            f"Hit List dedupe index: {len(existing_keys)} store keys, "
            f"{len(existing_pids)} place_ids in Notes, {len(existing_geo_name)} name+geo fingerprints, "
            f"{len(existing_name_addr)} name+address keys"
        )
    elif args.dry_run:
        try:
            gc_dry = gspread_client()
            ws0 = gc_dry.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
            existing_keys, existing_pids, existing_geo_name, existing_name_addr = extract_existing_for_dedupe(ws0)
            print(
                f"Dry-run: loaded Hit List — store keys: {len(existing_keys)}, "
                f"place_ids in Notes: {len(existing_pids)}, "
                f"name+geo fingerprints: {len(existing_geo_name)}, "
                f"name+address keys: {len(existing_name_addr)}"
            )
        except Exception as exc:
            existing_keys, existing_pids, existing_geo_name, existing_name_addr = set(), set(), set(), set()
            print(f"Dry-run: could not load Hit List ({exc}); dedupe vs existing rows disabled.")

    to_append: list[list[str]] = []
    stats = {
        "details": 0,
        "skip_box": 0,
        "skip_filter": 0,
        "skip_dup": 0,
        "skip_dup_geo": 0,
        "skip_dup_name_addr": 0,
        "skip_closed": 0,
    }

    for pid in sorted(seen_place_ids):
        if len(to_append) >= args.max_new:
            break
        if pid in existing_pids:
            stats["skip_dup"] += 1
            continue

        meta = nearby_meta.get(pid)
        if meta:
            n0, t0, v0 = meta
            bad0, _ = should_exclude(n0, t0, v0)
            if bad0:
                stats["skip_filter"] += 1
                continue

        det = place_details(key, pid)
        stats["details"] += 1
        time.sleep(max(0.0, args.sleep_details))

        if det.get("status") != "OK":
            continue
        res = det.get("result") or {}
        name = (res.get("name") or "").strip()
        if not name:
            continue
        if (res.get("business_status") or "") == "CLOSED_PERMANENTLY":
            stats["skip_closed"] += 1
            continue

        types = list(res.get("types") or [])
        vic = (res.get("vicinity") or "").strip()
        bad, why = should_exclude(name, types, vic)
        if bad:
            stats["skip_filter"] += 1
            continue

        loc = (res.get("geometry") or {}).get("location") or {}
        lat_f = loc.get("lat")
        lng_f = loc.get("lng")
        try:
            lat = float(lat_f) if lat_f is not None else None
            lng = float(lng_f) if lng_f is not None else None
        except (TypeError, ValueError):
            lat, lng = None, None

        if not (
            lat is not None
            and lng is not None
            and region.min_lat <= lat <= region.max_lat
            and region.min_lng <= lng <= region.max_lng
        ):
            stats["skip_box"] += 1
            continue

        parsed = parse_address_components(res.get("address_components") or [])
        formatted = (res.get("formatted_address") or "").strip()
        street = (parsed.get("street_line") or "").strip()
        if not street and formatted:
            street = formatted.split(",")[0].strip()
        city = parsed.get("city") or parsed.get("_neighborhood") or ""
        state = (parsed.get("state") or "").strip()
        if region.allowed_states is not None:
            if state not in region.allowed_states:
                stats["skip_box"] += 1
                continue
        elif state != (region.required_state or "CA"):
            stats["skip_box"] += 1
            continue
        if not city:
            city = region.fallback_city

        phone = (res.get("formatted_phone_number") or "").strip()
        website = (res.get("website") or "").strip()

        hours = opening_hours_week_grid_from_place_result(res)
        rd = row_dict_for_append(
            name=name,
            street=street,
            city=city,
            state=state,
            lat=lat,
            lng=lng,
            phone=phone,
            website=website,
            shop_type=args.shop_type,
            place_id=pid,
            region_notes_label=region.notes_label,
            opening_hours_row=hours,
            google_listing=google_listing_from_business_status(res.get("business_status")),
        )
        sk = rd["Store Key"]
        sk_legacy = compute_store_key_legacy(name, street, city, state)
        gfp = geo_name_fingerprint(name, lat, lng)
        if gfp and gfp in existing_geo_name:
            stats["skip_dup_geo"] += 1
            continue
        if sk in existing_keys or sk_legacy in existing_keys:
            stats["skip_dup"] += 1
            continue

        nafp = name_address_fingerprint(name, street)
        if nafp and nafp in existing_name_addr:
            stats["skip_dup_name_addr"] += 1
            continue

        to_append.append([rd[c] for c in HIT_LIST_COLS])
        existing_keys.add(sk)
        existing_keys.add(sk_legacy)
        if gfp:
            existing_geo_name.add(gfp)
        if nafp:
            existing_name_addr.add(nafp)

    print("\n--- Summary ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  new_rows_ready: {len(to_append)}")

    if args.dry_run:
        print("\nDry-run: first 15 proposed rows:")
        for i, row in enumerate(to_append[:15]):
            d = dict(zip(HIT_LIST_COLS, row))
            print(f"  {i+1}. {d['Shop Name']!r} | {d['City']}, {d['State']} | {d['Store Key']}")
        if len(to_append) > 15:
            print(f"  ... and {len(to_append) - 15} more")
        return

    if not to_append:
        print("Nothing to append.")
        return

    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    hdr = [str(x or "").strip() for x in ws.row_values(1)]
    missing_h = [c for c in HIT_LIST_OPENING_HOUR_COLS if c not in hdr]
    if missing_h:
        raise SystemExit(
            "Hit List row 1 is missing opening-hour column(s): "
            + ", ".join(missing_h)
            + ". Add them (after Contact Form URL) to match scripts/discover_apothecaries_la_hit_list.py, then re-run."
        )
    if GOOGLE_LISTING_COL not in hdr:
        next_col = len(hdr) + 1
        if ws.col_count < next_col:
            ws.add_cols(next_col - ws.col_count)
        ws.update_cell(1, next_col, GOOGLE_LISTING_COL)
        hdr.append(GOOGLE_LISTING_COL)
    ws.append_rows(to_append, value_input_option="USER_ENTERED")
    print(f"Appended {len(to_append)} rows to {HIT_LIST_WS!r}.")


if __name__ == "__main__":
    main()
