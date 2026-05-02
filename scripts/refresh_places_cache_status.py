#!/usr/bin/env python3
"""
Refresh the ``business_status`` of every record in ``TrueSightDAO/places-cache``.

The places-cache is permanent by design, but three Place Details fields decay
over time: ``business_status`` (stores can close), ``opening_hours``, and
``formatted_phone_number``. This sweep refreshes ``business_status`` cheaply
by re-calling Place Details with **Basic-tier fields only** (free SKU on the
legacy Places API) for every cached record. Contact-tier fields (phone /
website / hours) in the cached record are left untouched — they were paid
for once and don't decay fast enough to justify re-paying.

Run on a cron / manually:

    cd market_research
    python3 scripts/refresh_places_cache_status.py --dry-run
    python3 scripts/refresh_places_cache_status.py --limit 200
    python3 scripts/refresh_places_cache_status.py             # full sweep

Exits with the count of records refreshed and the count flagged
``CLOSED_PERMANENTLY`` so the operator can act on closures.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from places_cache import (  # noqa: E402
    CACHE_REPO_BRANCH,
    CACHE_REPO_NAME,
    CACHE_REPO_OWNER,
    CONTENTS_API,
    PLACES_DETAILS_URL,
    _fetch_cached_record,
    _write_cached_record,
    _write_token,
    BASIC_FIELDS,
)


TREES_API = (
    f"https://api.github.com/repos/{CACHE_REPO_OWNER}/{CACHE_REPO_NAME}/git/trees"
)


def list_cached_place_ids() -> list[str]:
    """Return every cached place_id by walking the repo tree once.

    Uses the recursive trees API which returns the whole tree in one call.
    GitHub caps that response at 100k entries — for places-cache (one file
    per place_id, ~3-5KB each) this is plenty of headroom.
    """
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
        return []
    payload = r.json()
    if payload.get("truncated"):
        sys.stderr.write(
            "WARNING: tree response truncated. Cache has >100k records — implement pagination.\n"
        )
    out = []
    for item in payload.get("tree", []) or []:
        if item.get("type") != "blob":
            continue
        path = item.get("path", "")
        if not path.startswith("places/"):
            continue
        if not path.endswith(".json"):
            continue
        # Path shape: places/<prefix>/<place_id>.json
        parts = path.split("/")
        if len(parts) != 3:
            continue
        place_id = parts[-1][:-len(".json")]
        if place_id and place_id != ".gitkeep":
            out.append(place_id)
    return out


def refresh_basic_fields(api_key: str, place_id: str) -> dict | None:
    """Hit Place Details with Basic-only fields. Returns ``result`` or None on error."""
    params = {
        "place_id": place_id,
        "fields": ",".join(BASIC_FIELDS),
        "key": api_key,
    }
    try:
        r = requests.get(PLACES_DETAILS_URL, params=params, timeout=30)
    except requests.RequestException as e:
        sys.stderr.write(f"refresh: live failed for {place_id}: {e}\n")
        return None
    if r.status_code != 200:
        sys.stderr.write(f"refresh: HTTP {r.status_code} for {place_id}: {r.text[:200]}\n")
        return None
    data = r.json()
    status = data.get("status")
    if status == "NOT_FOUND":
        # Place removed by Google — flag in the record so operator notices.
        return {"_status": "NOT_FOUND", "place_id": place_id}
    if status != "OK":
        sys.stderr.write(f"refresh: status {status!r} for {place_id}\n")
        return None
    return data.get("result") or {}


def merge_basic_into_record(rec: dict, fresh_basic: dict) -> tuple[dict, str]:
    """Update Basic-tier fields in the cached record without touching Contact /
    Atmosphere fields. Returns (new_record, change_summary).
    """
    cached_result = (rec.get("result") or {}).copy()
    change_bits = []

    if fresh_basic.get("_status") == "NOT_FOUND":
        cached_result["business_status"] = "NOT_FOUND_BY_GOOGLE"
        change_bits.append("flagged NOT_FOUND")
    else:
        for field in BASIC_FIELDS:
            new_val = fresh_basic.get(field)
            if new_val is None:
                continue
            old_val = cached_result.get(field)
            if old_val != new_val:
                if field == "business_status":
                    change_bits.append(f"business_status: {old_val!r} → {new_val!r}")
                else:
                    change_bits.append(field)
                cached_result[field] = new_val

    new_rec = dict(rec)
    new_rec["result"] = cached_result
    new_rec["last_status_refresh_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return new_rec, ", ".join(change_bits) if change_bits else "no changes"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None,
                   help="Max records to refresh in this run (default: all).")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would change without writing.")
    p.add_argument("--sleep", type=float, default=0.1,
                   help="Sleep between live calls in seconds (default 0.1).")
    args = p.parse_args(argv)

    api_key = (
        os.environ.get("GOOGLE_MAPS_API_KEY")
        or os.environ.get("GOOGLE_PLACES_API_KEY", "")
    )
    if not api_key:
        sys.stderr.write("Set GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY in env / .env\n")
        return 1

    place_ids = list_cached_place_ids()
    print(f"Found {len(place_ids)} cached records.", flush=True)
    if args.limit is not None:
        place_ids = place_ids[: args.limit]
        print(f"Limiting to first {len(place_ids)} for this run.", flush=True)

    refreshed = 0
    closed_count = 0
    not_found_count = 0
    write_failures = 0

    for i, pid in enumerate(place_ids, start=1):
        rec, sha = _fetch_cached_record(pid)
        if not rec:
            sys.stderr.write(f"  [{i}/{len(place_ids)}] {pid}: read failed; skipping\n")
            continue
        fresh = refresh_basic_fields(api_key, pid)
        if fresh is None:
            sys.stderr.write(f"  [{i}/{len(place_ids)}] {pid}: live call failed; skipping\n")
            continue
        new_rec, change_summary = merge_basic_into_record(rec, fresh)
        if "CLOSED_PERMANENTLY" in str(new_rec.get("result", {}).get("business_status", "")):
            closed_count += 1
        if new_rec.get("result", {}).get("business_status") == "NOT_FOUND_BY_GOOGLE":
            not_found_count += 1
        print(f"  [{i}/{len(place_ids)}] {pid}: {change_summary}", flush=True)
        if args.dry_run:
            continue
        if change_summary == "no changes":
            # Still touch last_status_refresh_at? Yes — record that we checked.
            pass
        ok = _write_cached_record(pid, new_rec, sha)
        if ok:
            refreshed += 1
        else:
            write_failures += 1
        time.sleep(max(0.0, args.sleep))

    print()
    print(f"Refreshed:     {refreshed}")
    print(f"Closed perm:   {closed_count}")
    print(f"Not found:     {not_found_count}")
    print(f"Write failed:  {write_failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
