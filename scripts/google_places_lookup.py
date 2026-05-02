#!/usr/bin/env python3
"""
Look up a place with Google Places API (Find Place + Place Details).

Reads GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY from market_research/.env
(same key as agroverse_shop/js/config.js).

Example:
  cd market_research
  python scripts/google_places_lookup.py "Empress Organics" --lat 33.9597671 --lng -118.324935

Note:
  Keys used in the Agroverse *browser* are often restricted to HTTP referrers. The Places *web service*
  from this script counts as server use — Google returns REQUEST_DENIED unless the key allows your IP
  (or you use an unrestricted dev key). Create a second API key with IP restriction for CLI workflows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


def api_key() -> str:
    load_dotenv_file(ROOT / ".env")
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    k = os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")
    if not k:
        print(
            "Set GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY) in market_research/.env",
            file=sys.stderr,
        )
        sys.exit(1)
    return k


def find_place(
    key: str, text: str, lat: float | None, lng: float | None, radius_m: float
) -> dict:
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params: dict = {
        "input": text,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,business_status,geometry",
        "key": key,
    }
    if lat is not None and lng is not None:
        params["locationbias"] = f"circle:{int(radius_m)}@{lat},{lng}"
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def place_details(key: str, place_id: str) -> dict:
    """Place Details lookup, served from the persistent places-cache repo.

    Delegates to ``places_cache.cached_place_details_full`` so repeated
    lookups for the same ``place_id`` from any caller (locally or in CI) cost
    nothing after the first hit. Atmosphere fields (rating / user_ratings_total)
    are not requested — a 2026-05-01 audit confirmed nobody reads them, and
    skipping that tier saves $5/1k per Details call.

    Return shape preserved for backward compatibility: ``{"status": "OK"|"...",
    "result": {...}}``. Consumers that already check ``status == "OK"`` keep
    working unchanged.
    """
    # Lazy import to avoid a circular if places_cache imports back.
    from places_cache import cached_place_details_full
    result = cached_place_details_full(key, place_id)
    if not result:
        return {"status": "ZERO_RESULTS", "result": {}}
    return {"status": "OK", "result": result}


def main() -> None:
    p = argparse.ArgumentParser(description="Google Places find + details")
    p.add_argument("query", help="Place name or text query")
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lng", type=float, default=None)
    p.add_argument("--radius", type=float, default=500.0, help="Bias circle radius in meters")
    args = p.parse_args()

    key = api_key()
    find_json = find_place(key, args.query, args.lat, args.lng, args.radius)
    st = find_json.get("status")
    if st not in ("OK",):
        print(json.dumps(find_json, indent=2), file=sys.stderr)
        if find_json.get("error_message") and "referer" in find_json["error_message"].lower():
            print(
                "\nThis usually means GOOGLE_MAPS_API_KEY is browser-only (HTTP referrer restriction). "
                "Use a server/IP-restricted Places key in .env for this script.\n",
                file=sys.stderr,
            )
        sys.exit(1 if st not in ("ZERO_RESULTS",) else 2)

    cands = find_json.get("candidates") or []
    if not cands:
        print(json.dumps(find_json, indent=2))
        sys.exit(1)

    place_id = cands[0].get("place_id")
    out = {"find_place": find_json, "details": place_details(key, place_id) if place_id else None}

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
