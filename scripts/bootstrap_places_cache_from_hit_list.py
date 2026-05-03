#!/usr/bin/env python3
"""
Bootstrap the places-cache from data already on the Hit List sheet.

Background: per Gary 2026-05-03 — "if existing records on the Hit List
are considered complete, why not just cache them already on Github?"

The Hit List has hundreds of rows whose Place Details fields (Address,
Phone, Website, Lat/Lng, opening hours) are already populated from prior
operator work + earlier API calls. Without bootstrapping, every place_id
still has to be re-fetched live the first time any cron asks for it,
even though we *already* know the answer. This script walks the Hit List
once, synthesizes a Place Details cache record from the sheet's columns,
and writes to TrueSightDAO/places-cache so future calls hit cache from
the start.

What's synthesized per row (only fields the sheet actually has):
  - place_id              ← extracted from Notes (PLACE_ID_IN_NOTES regex)
  - name                  ← Shop Name
  - formatted_address     ← Address + City + State (joined)
  - formatted_phone_number ← Phone
  - website               ← Website
  - geometry.location     ← Latitude + Longitude
  - opening_hours.weekday_text ← Monday Open/Close … Sunday Open/Close

What's NOT synthesized (because the sheet doesn't carry it):
  - address_components (structured), types, business_status, photos,
    plus_code, vicinity, url, place icon URLs, etc.

Cache record's ``fields_requested`` is set to *only* what we synthesized,
so any consumer that asks for fields outside that set will correctly
cache-miss and trigger a live re-fetch for the union — same behavior as
a partial-coverage cache record.

Idempotent: skips place_ids that already have a cache record (avoids
overwriting better Google data with our synthesized version). Pass
``--force`` to overwrite anyway.

Usage:
    cd market_research
    python3 scripts/bootstrap_places_cache_from_hit_list.py --dry-run
    python3 scripts/bootstrap_places_cache_from_hit_list.py --limit 50
    python3 scripts/bootstrap_places_cache_from_hit_list.py             # full sweep
    python3 scripts/bootstrap_places_cache_from_hit_list.py --force     # overwrite
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from places_cache import (  # noqa: E402
    CACHE_REPO_BRANCH,
    CACHE_REPO_NAME,
    CACHE_REPO_OWNER,
    _fetch_cached_record,
    _write_cached_record,
    _write_token,
)

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

PLACE_ID_IN_NOTES = re.compile(r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})")
TREES_API = (
    f"https://api.github.com/repos/{CACHE_REPO_OWNER}/{CACHE_REPO_NAME}/git/trees"
)

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def already_cached_place_ids() -> set[str]:
    """Pull every place_id currently in places-cache via the Trees API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _write_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{TREES_API}/{CACHE_REPO_BRANCH}?recursive=1"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        sys.stderr.write(f"trees API HTTP {r.status_code}: {r.text[:200]}\n")
        return set()
    out: set[str] = set()
    for item in r.json().get("tree", []) or []:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if not path.startswith("places/") or not path.endswith(".json"):
            continue
        parts = path.split("/")
        if len(parts) != 3:
            continue
        pid = parts[-1][: -len(".json")]
        if pid and pid != ".gitkeep":
            out.add(pid)
    return out


def cell(row: list[str], idx_map: dict[str, int], name: str) -> str:
    i = idx_map.get(name, -1)
    if i < 0 or i >= len(row):
        return ""
    return (row[i] or "").strip()


def synthesize_result(row: list[str], idx_map: dict[str, int], place_id: str) -> tuple[dict, list[str]]:
    """Build a Place Details ``result`` dict from sheet columns.

    Returns (result, fields_requested). ``fields_requested`` lists only
    the fields we synthesized — consumers needing other fields will
    correctly cache-miss and refetch.
    """
    result: dict = {"place_id": place_id}
    fields: list[str] = ["place_id"]

    name = cell(row, idx_map, "Shop Name")
    if name:
        result["name"] = name
        fields.append("name")

    addr_parts = []
    for col_name in ("Address", "City", "State"):
        v = cell(row, idx_map, col_name)
        if v:
            addr_parts.append(v)
    if addr_parts:
        result["formatted_address"] = ", ".join(addr_parts)
        fields.append("formatted_address")

    phone = cell(row, idx_map, "Phone")
    if phone:
        result["formatted_phone_number"] = phone
        fields.append("formatted_phone_number")

    website = cell(row, idx_map, "Website")
    if website:
        result["website"] = website
        fields.append("website")

    lat_s = cell(row, idx_map, "Latitude")
    lng_s = cell(row, idx_map, "Longitude")
    if lat_s and lng_s:
        try:
            lat = float(lat_s)
            lng = float(lng_s)
            result["geometry"] = {"location": {"lat": lat, "lng": lng}}
            fields.append("geometry")
        except ValueError:
            pass

    weekday_text: list[str] = []
    has_any_hours = False
    for day in DAYS:
        opn = cell(row, idx_map, f"{day} Open")
        cls = cell(row, idx_map, f"{day} Close")
        if opn and cls:
            weekday_text.append(f"{day}: {opn} – {cls}")
            has_any_hours = True
        else:
            weekday_text.append(f"{day}: Closed")
    if has_any_hours:
        result["opening_hours"] = {"weekday_text": weekday_text}
        fields.append("opening_hours")

    return result, fields


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None,
                   help="Cap number of rows synthesized this run (default: all).")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be written without touching places-cache.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing cache records (default: skip place_ids already cached).")
    p.add_argument("--sleep", type=float, default=0.05,
                   help="Sleep between writes in seconds (default 0.05; rate-limit safety).")
    args = p.parse_args(argv)

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return 0
    header = [str(x or "").strip() for x in rows[0]]
    idx_map = {h: i for i, h in enumerate(header)}
    if "Notes" not in idx_map:
        sys.stderr.write("Hit List missing required 'Notes' column.\n")
        return 1

    print(f"Hit List rows: {len(rows) - 1}", flush=True)
    existing = set() if args.force else already_cached_place_ids()
    print(f"Already cached: {len(existing)}", flush=True)

    written = 0
    skipped_no_pid = 0
    skipped_already_cached = 0
    skipped_no_synth = 0
    failures = 0

    for ri, raw in enumerate(rows[1:], start=2):
        if args.limit is not None and written >= args.limit:
            break
        row = list(raw) + [""] * (len(header) - len(raw))
        notes = cell(row, idx_map, "Notes")
        m = PLACE_ID_IN_NOTES.search(notes)
        if not m:
            skipped_no_pid += 1
            continue
        pid = m.group(1).strip()
        if not args.force and pid in existing:
            skipped_already_cached += 1
            continue

        result, fields = synthesize_result(row, idx_map, pid)
        if len(fields) <= 1:  # only place_id, no other useful data
            skipped_no_synth += 1
            continue

        record = {
            "place_id": pid,
            "name": result.get("name", ""),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fields_requested": fields,
            "google_status": "OK",
            "result": result,
            "_source": "bootstrap_from_hit_list",
        }

        if args.dry_run:
            print(f"  [dry] row {ri} → cache {pid}: fields={fields}", flush=True)
            written += 1
            continue

        # Pass prior_sha if the file already exists (force-overwrite case).
        prior_sha = None
        if args.force and pid in existing:
            _, prior_sha = _fetch_cached_record(pid)
        ok = _write_cached_record(pid, record, prior_sha)
        if ok:
            written += 1
            print(f"  [write] row {ri} → cached {pid} ({len(fields)} fields)", flush=True)
            time.sleep(max(0.0, args.sleep))
        else:
            failures += 1

    print()
    print(f"Bootstrapped:        {written}")
    print(f"Skipped (no place_id in Notes): {skipped_no_pid}")
    print(f"Skipped (already cached):       {skipped_already_cached}")
    print(f"Skipped (no fields to synth):   {skipped_no_synth}")
    print(f"Write failures:      {failures}")
    if not args.dry_run and written > 0:
        print()
        print(f"places-cache repo: https://github.com/{CACHE_REPO_OWNER}/{CACHE_REPO_NAME}/commits/{CACHE_REPO_BRANCH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
