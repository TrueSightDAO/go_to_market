#!/usr/bin/env python3
"""
Discover apothecary-like stores in greater Los Angeles via Google Places Nearby Search,
pre-filter obvious pharmacies / cannabis retail, dedupe against the live Hit List, then
append new rows with Status=Research for scripts/hit_list_research_photo_review.py (CI).

Requires:
  - GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY in market_research/.env (server/IP key)
  - google_credentials.json with Editor access to the Hit List spreadsheet

Usage:
  cd market_research
  python3 scripts/discover_apothecaries_la_hit_list.py --dry-run
  python3 scripts/discover_apothecaries_la_hit_list.py --max-new 80

Nearby Search uses multiple centroids so 50km circles cover the metro; results are
deduped by place_id. Rows outside an LA-ish bounding box are skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
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
]

# Greater LA metro — centers (lat, lng), meters. Google Nearby max radius is 50000.
SEARCH_CENTERS: list[tuple[float, float, int, str]] = [
    (34.052235, -118.243683, 50000, "Downtown LA"),
    (34.019481, -118.491227, 50000, "Santa Monica"),
    (34.147785, -118.144516, 50000, "Pasadena"),
    (33.770050, -118.193739, 50000, "Long Beach"),
    (34.180840, -118.308967, 50000, "Burbank/Glendale"),
    (33.835849, -118.340628, 50000, "Torrance"),
    (34.068621, -117.937035, 45000, "West Covina"),
    (34.278289, -118.745441, 45000, "Simi Valley / NW valley"),
]

# Rough bounding box: drop obvious out-of-region Nearby leakage (CA desert, etc.)
LA_MIN_LAT, LA_MAX_LAT = 33.35, 35.05
LA_MIN_LNG, LA_MAX_LNG = -119.05, -117.20

NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

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
    }
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


def compute_store_key(name: str, street: str, city: str, state: str) -> str:
    return (
        f"{slug_segment(name)}__{slug_segment(street)}__"
        f"{slug_segment(city)}__{slug_segment(state)}"
    )


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
        "types,address_component,business_status,url"
    )
    r = requests.get(
        DETAILS_URL,
        params={"place_id": place_id, "fields": fields, "key": key},
        timeout=45,
    )
    r.raise_for_status()
    return r.json()


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


def extract_existing_keys_and_place_ids(ws: gspread.Worksheet) -> tuple[set[str], set[str]]:
    rows = ws.get_all_values()
    if len(rows) < 2:
        return set(), set()
    header = rows[0]
    try:
        sk_i = header.index("Store Key")
    except ValueError:
        sk_i = -1
    keys: set[str] = set()
    place_ids: set[str] = set()
    pid_re = re.compile(r"place_id:\s*([A-Za-z0-9_-]+)")
    for row in rows[1:]:
        if sk_i >= 0 and sk_i < len(row):
            k = row[sk_i].strip()
            if k:
                keys.add(k)
        notes = ""
        try:
            ni = header.index("Notes")
            if ni < len(row):
                notes = row[ni]
        except ValueError:
            pass
        for m in pid_re.finditer(notes or ""):
            place_ids.add(m.group(1).strip())
    return keys, place_ids


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
) -> dict[str, str]:
    notes = (
        f"Auto-discovered (Google Places Nearby, LA metro). place_id: {place_id}. "
        "Pre-filtered pharmacies/cannabis chains; confirm shop type before outreach."
    )
    sk = compute_store_key(name, street, city, state)
    return {
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
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Discover LA apothecaries via Places, filter, append Hit List (Research)."
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

    key = maps_api_key()
    seen_place_ids: set[str] = set()
    raw_results: list[dict[str, Any]] = []

    for lat, lng, radius, label in SEARCH_CENTERS:
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
    if gc is not None:
        ws0 = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
        existing_keys, existing_pids = extract_existing_keys_and_place_ids(ws0)
        print(f"Hit List existing Store Keys: {len(existing_keys)}, place_ids in Notes: {len(existing_pids)}")
    elif args.dry_run:
        try:
            gc_dry = gspread_client()
            ws0 = gc_dry.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
            existing_keys, existing_pids = extract_existing_keys_and_place_ids(ws0)
            print(
                f"Dry-run: loaded Hit List — Store Keys: {len(existing_keys)}, "
                f"place_ids in Notes: {len(existing_pids)}"
            )
        except Exception as exc:
            existing_keys, existing_pids = set(), set()
            print(f"Dry-run: could not load Hit List ({exc}); dedupe vs existing rows disabled.")

    to_append: list[list[str]] = []
    stats = {"details": 0, "skip_box": 0, "skip_filter": 0, "skip_dup": 0, "skip_closed": 0}

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

        if not (lat is not None and lng is not None and LA_MIN_LAT <= lat <= LA_MAX_LAT and LA_MIN_LNG <= lng <= LA_MAX_LNG):
            stats["skip_box"] += 1
            continue

        parsed = parse_address_components(res.get("address_components") or [])
        formatted = (res.get("formatted_address") or "").strip()
        street = (parsed.get("street_line") or "").strip()
        if not street and formatted:
            street = formatted.split(",")[0].strip()
        city = parsed.get("city") or parsed.get("_neighborhood") or ""
        state = (parsed.get("state") or "").strip()
        if state != "CA":
            stats["skip_box"] += 1
            continue
        if not city:
            city = "Los Angeles"

        phone = (res.get("formatted_phone_number") or "").strip()
        website = (res.get("website") or "").strip()

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
        )
        sk = rd["Store Key"]
        if sk in existing_keys:
            stats["skip_dup"] += 1
            continue

        to_append.append([rd[c] for c in HIT_LIST_COLS])
        existing_keys.add(sk)

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
    ws.append_rows(to_append, value_input_option="USER_ENTERED")
    print(f"Appended {len(to_append)} rows to {HIT_LIST_WS!r}.")


if __name__ == "__main__":
    main()
