#!/usr/bin/env python3
"""
Permanent cache for Google Places API responses, backed by the
``TrueSightDAO/places-cache`` GitHub repo via the Contents API.

The Places API charges per call. A single ``place_id`` rarely changes, but
the codebase used to re-pay for the same lookup every time a script ran.
This module reads cached responses from the cache repo via the GitHub
Contents API (or via raw.githubusercontent.com for read-only use), only
hits the live API on a miss, and writes the response back to the cache
repo so the next caller — local, CI, or anyone — gets it free.

The cache is **permanent**: cached records do not expire. Three fields
decay (``business_status``, ``opening_hours``, ``formatted_phone_number``)
and need a separate cheap refresh sweep using only Basic-tier fields. That
sweep lives in the cache repo, not here.

Field tiers (Places Details API legacy pricing):
  - Basic   ($17/1k):  place_id, name, formatted_address, geometry, types,
                       address_component, business_status, vicinity, photos,
                       url, plus_code, icon, …
  - Contact (+$3/1k):  formatted_phone_number, website, opening_hours,
                       international_phone_number, current_opening_hours
  - Atmosphere (+$5/1k): rating, user_ratings_total, reviews, price_level

A 2026-05-01 audit of every caller in the codebase confirmed ``rating``,
``user_ratings_total``, ``reviews`` are NEVER read out of any response. The
canonical helper now never requests them, saving ~25% per Details call.

Two helpers:
  - ``cached_place_details_lite(key, place_id)``
      Basic fields only. Use when you only need photos, types, business
      status, geometry — i.e. when you don't need phone/website/hours.
  - ``cached_place_details_full(key, place_id)``
      Basic + Contact. The default for enrichment / discovery work that
      needs phone, website, opening hours.

Both check the cache first; on miss, fetch from Places, then write to the
cache repo. On a cache hit where ``fields_requested`` already covers what's
needed, the live call is skipped entirely.

Usage:
    from places_cache import cached_place_details_full

    res = cached_place_details_full(api_key, place_id)
    # res is the Places Details "result" dict (or {} on hard error).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests


CACHE_REPO_OWNER = "TrueSightDAO"
CACHE_REPO_NAME = "places-cache"
CACHE_REPO_BRANCH = "main"

CONTENTS_API = (
    f"https://api.github.com/repos/{CACHE_REPO_OWNER}/{CACHE_REPO_NAME}/contents"
)
RAW_BASE = (
    f"https://raw.githubusercontent.com/{CACHE_REPO_OWNER}/{CACHE_REPO_NAME}/"
    f"{CACHE_REPO_BRANCH}"
)
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Field sets — KEEP IN SYNC with the README in the cache repo.
BASIC_FIELDS = (
    "place_id",
    "name",
    "formatted_address",
    "geometry",
    "types",
    "address_component",
    "business_status",
    "vicinity",
    "photos",
    "url",
)
CONTACT_FIELDS = (
    "formatted_phone_number",
    "website",
    "opening_hours",
)
# Atmosphere fields intentionally omitted (audit 2026-05-01: never consumed).

LITE_FIELDS = BASIC_FIELDS
FULL_FIELDS = BASIC_FIELDS + CONTACT_FIELDS

# Where to look for the write token. PLACES_CACHE_PAT first; falls back to
# the broader oracle PATs if available (those have access too).
TOKEN_ENV_VARS = (
    "PLACES_CACHE_PAT",
    "TRUESIGHT_DAO_ORACLE_ADVISORY_PAT",
    "ORACLE_ADVISORY_PUSH_TOKEN",
)


def _load_dotenv(path: Path) -> None:
    """Mini .env loader; doesn't override existing env vars."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if k and k not in os.environ:
            os.environ[k] = v


# Load the local .env if present so callers don't need to load it themselves.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_load_dotenv(_REPO_ROOT / ".env")


def _write_token() -> str | None:
    for v in TOKEN_ENV_VARS:
        tok = os.environ.get(v, "").strip()
        if tok:
            return tok
    return None


def _cache_path(place_id: str) -> str:
    """Layout: places/<2-char-prefix>/<place_id>.json"""
    pid = place_id.strip()
    if not pid:
        raise ValueError("place_id is empty")
    prefix = pid[:2] if len(pid) >= 2 else pid
    return f"places/{prefix}/{pid}.json"


def _fetch_cached_record(place_id: str) -> tuple[dict | None, str | None]:
    """Return (record_dict, sha) or (None, None) on miss / error.

    Reads via the GitHub Contents API rather than raw.githubusercontent.com
    because raw is fronted by a CDN with up to ~5-minute staleness — that
    produced false cache-misses immediately after a write, and write retries
    then failed with 422 ("sha wasn't supplied"). The Contents API is
    real-time and returns the file content + sha in one response, which is
    exactly what the writer needs anyway.

    Authenticated requests get 5000 reads/hour, far above any plausible
    cache hit rate.
    """
    path = _cache_path(place_id)
    api_url = f"{CONTENTS_API}/{path}?ref={CACHE_REPO_BRANCH}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _write_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = requests.get(api_url, headers=headers, timeout=15)
    except requests.RequestException:
        return None, None
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        sys.stderr.write(
            f"places_cache: read HTTP {r.status_code} for {place_id}: {r.text[:200]}\n"
        )
        return None, None

    payload = r.json()
    sha = payload.get("sha")
    encoded = payload.get("content", "")
    if not encoded:
        return None, sha
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        rec = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None, sha
    return rec, sha


def _write_cached_record(place_id: str, record: dict, prior_sha: str | None) -> bool:
    """PUT the record to the cache repo via Contents API. True on success."""
    token = _write_token()
    if not token:
        sys.stderr.write(
            "places_cache: no PLACES_CACHE_PAT (or fallback) set; skipping cache write\n"
        )
        return False
    path = _cache_path(place_id)
    body = {
        "message": f"cache: {place_id}",
        "content": base64.b64encode(
            json.dumps(record, indent=2, sort_keys=True).encode("utf-8")
        ).decode("ascii"),
        "branch": CACHE_REPO_BRANCH,
    }
    if prior_sha:
        body["sha"] = prior_sha
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.put(f"{CONTENTS_API}/{path}", headers=headers, json=body, timeout=30)
    except requests.RequestException as e:
        sys.stderr.write(f"places_cache: write failed for {place_id}: {e}\n")
        return False
    if r.status_code in (200, 201):
        return True
    # 409 = sha mismatch (someone else wrote in the meantime); refetch + retry once.
    if r.status_code == 409 and prior_sha:
        _, fresh_sha = _fetch_cached_record(place_id)
        if fresh_sha and fresh_sha != prior_sha:
            body["sha"] = fresh_sha
            try:
                r2 = requests.put(f"{CONTENTS_API}/{path}", headers=headers, json=body, timeout=30)
                if r2.status_code in (200, 201):
                    return True
            except requests.RequestException:
                pass
    sys.stderr.write(
        f"places_cache: write rejected for {place_id} ({r.status_code}): {r.text[:200]}\n"
    )
    return False


# Process-level circuit breaker: once the Places API tells us we're rate
# limited (OVER_QUERY_LIMIT) or quota-blocked, stop hammering it for the
# rest of this process. Otherwise a script with a long row queue will
# burn through the entire queue making failed live calls — every miss
# returning "" because the cache wasn't populated, then the next miss
# hitting the same wall. Reset by restarting the process; until then
# all cached_place_details() callers get an empty result without a live
# call, and the caller can choose to bail or queue for later.
_RATE_LIMITED = False


def is_rate_limited() -> bool:
    """True after any live Places call returned OVER_QUERY_LIMIT or REQUEST_DENIED.

    Callers running long sweeps should check this between iterations and
    bail out — there's no point continuing to attempt live calls once the
    quota wall is up.
    """
    return _RATE_LIMITED


# Statuses Google returns that mean "definitive negative — Google has
# nothing for this place_id, hitting again will return the same answer."
# Cached as negative records so the next call short-circuits without a
# live API hit.
_NEGATIVE_STATUSES = ("NOT_FOUND", "ZERO_RESULTS", "INVALID_REQUEST")

# Statuses that mean "we hit the rate / quota wall." NOT cached because
# the data might be available after quota refreshes. Tripping the
# circuit breaker keeps the rest of this process from making more
# wasted live calls.
_RATE_LIMIT_STATUSES = ("OVER_QUERY_LIMIT", "REQUEST_DENIED", "RESOURCE_EXHAUSTED")


def _live_place_details(api_key: str, place_id: str, fields: tuple[str, ...]) -> tuple[dict, str]:
    """Hit Places Details API; return ``(result_dict, google_status)``.

    Statuses:
      - ``"OK"`` — result dict is non-empty (may have missing fields).
      - One of ``_NEGATIVE_STATUSES`` — definitive: Google has nothing.
        Result dict is ``{}``; caller should cache as a negative record.
      - One of ``_RATE_LIMIT_STATUSES`` — rate-limited. Trips the
        process-level circuit breaker so subsequent calls return empty
        without hitting the API.
      - ``""`` — transport failure (HTTP non-200, RequestException, etc.).
        Caller should NOT cache; this is transient.
    """
    global _RATE_LIMITED
    if _RATE_LIMITED:
        return {}, ""

    params = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": api_key,
    }
    try:
        r = requests.get(PLACES_DETAILS_URL, params=params, timeout=30)
    except requests.RequestException as e:
        sys.stderr.write(f"places_cache: live call failed for {place_id}: {e}\n")
        return {}, ""
    if r.status_code != 200:
        sys.stderr.write(
            f"places_cache: live HTTP {r.status_code} for {place_id}: {r.text[:200]}\n"
        )
        return {}, ""
    data = r.json()
    status = data.get("status") or ""
    if status == "OK":
        return (data.get("result") or {}), "OK"
    if status in _RATE_LIMIT_STATUSES:
        _RATE_LIMITED = True
        sys.stderr.write(
            f"places_cache: live status {status!r} for {place_id} — "
            f"tripping process-level rate-limit circuit breaker; subsequent "
            f"cache misses in this process will return empty without a live call.\n"
        )
        return {}, status
    if status in _NEGATIVE_STATUSES:
        # Definitive negative — caller will cache so we never re-pay.
        sys.stderr.write(
            f"places_cache: live status {status!r} for {place_id} — "
            f"caching as negative record so future calls short-circuit.\n"
        )
        return {}, status
    # Unknown status — log and don't cache; treat as transient.
    sys.stderr.write(
        f"places_cache: live status {status!r} for {place_id} (unknown — not cached)\n"
    )
    return {}, ""


def _record_satisfies(record: dict, needed: tuple[str, ...]) -> bool:
    have = set(record.get("fields_requested") or [])
    return have.issuperset(set(needed))


def cached_place_details(
    api_key: str, place_id: str, *, fields: tuple[str, ...], refresh: bool = False
) -> dict:
    """Core lookup. Returns the Places Details `result` dict.

    Cache-hit path:
      - If cached record's ``google_status`` is a definitive negative
        (NOT_FOUND / ZERO_RESULTS / INVALID_REQUEST), return ``{}`` immediately
        — no live call, no re-pay.
      - If cached ``fields_requested`` covers ``fields``, return cached
        ``result`` (no live call).

    Cache-miss path:
      - Fetch live for the union of cached + requested fields.
      - Write back: a successful OK becomes a positive record; a definitive
        negative status becomes a negative record so future calls
        short-circuit; rate-limited / transport-failure responses are NOT
        cached (might succeed later).
    """
    pid = (place_id or "").strip()
    if not pid:
        return {}

    cached_rec, sha = (None, None) if refresh else _fetch_cached_record(pid)
    if cached_rec:
        cached_status = cached_rec.get("google_status", "OK")
        # Definitive-negative cache hit → don't bother the API again.
        if cached_status in _NEGATIVE_STATUSES:
            return {}
        if cached_status == "OK" and _record_satisfies(cached_rec, fields):
            return cached_rec.get("result") or {}

    # On a partial-coverage hit, fetch the union so we don't lose existing fields.
    union = tuple(sorted(set(fields) | set((cached_rec or {}).get("fields_requested") or [])))

    fresh, status = _live_place_details(api_key, pid, union)

    if status == "OK" and fresh:
        record = {
            "place_id": pid,
            "name": fresh.get("name", ""),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fields_requested": list(union),
            "google_status": "OK",
            "result": fresh,
        }
        _write_cached_record(pid, record, sha)
        return fresh

    if status in _NEGATIVE_STATUSES:
        # Cache the definitive negative so the next call short-circuits.
        # Only write if we don't already have a (better) cached record.
        if not cached_rec:
            negative_record = {
                "place_id": pid,
                "name": "",
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fields_requested": list(union),
                "google_status": status,
                "result": None,
            }
            _write_cached_record(pid, negative_record, sha)
        return {}

    # status is "" (transport / unknown) or rate-limited — DO NOT cache.
    # If we have any positive cache, return it as best-effort.
    return (cached_rec or {}).get("result") or {}


def cached_place_details_lite(api_key: str, place_id: str, *, refresh: bool = False) -> dict:
    """Basic-tier fields only ($17/1k flat). Use for photo / type / geometry needs."""
    return cached_place_details(api_key, place_id, fields=LITE_FIELDS, refresh=refresh)


def cached_place_details_full(api_key: str, place_id: str, *, refresh: bool = False) -> dict:
    """Basic + Contact ($20/1k). Default for enrichment with phone / website / hours."""
    return cached_place_details(api_key, place_id, fields=FULL_FIELDS, refresh=refresh)


# ---- Nearby Search coverage cache -----------------------------------------
#
# Nearby Search at $32/1k is the most expensive Places endpoint we hit. The
# discovery pipeline iterates ~50+ centroids per region and re-runs land on
# the same centroids; without a coverage cache, every re-run repays for
# already-discovered geography. The cache below stores the raw Nearby result
# list per (keyword, lat, lng, radius_m) combo so re-runs short-circuit and
# return the cached results — same dedup / Place Details flow downstream.
#
# Layout in the cache repo:
#   coverage/nearby/<sanitized_combo>.json
# where sanitized_combo encodes lat/lng/radius/keyword.
#
# Permanent by default; pass ``refresh=True`` to bypass and re-search a combo.

NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def _coverage_path(keyword: str, lat: float, lng: float, radius_m: int) -> str:
    safe_kw = (
        "".join(c if c.isalnum() else "_" for c in (keyword or "").strip().lower())
        or "nokeyword"
    )
    fname = f"{safe_kw}__lat{lat:.4f}_lng{lng:.4f}_r{int(radius_m)}m.json"
    return f"coverage/nearby/{fname}"


def _fetch_coverage_record(combo_path: str) -> tuple[dict | None, str | None]:
    api_url = f"{CONTENTS_API}/{combo_path}?ref={CACHE_REPO_BRANCH}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _write_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(api_url, headers=headers, timeout=15)
    except requests.RequestException:
        return None, None
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        return None, None
    payload = r.json()
    sha = payload.get("sha")
    encoded = payload.get("content", "")
    if not encoded:
        return None, sha
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        return json.loads(decoded), sha
    except (ValueError, json.JSONDecodeError):
        return None, sha


def _write_coverage_record(combo_path: str, record: dict, prior_sha: str | None) -> bool:
    token = _write_token()
    if not token:
        return False
    body = {
        "message": f"coverage: {combo_path.split('/')[-1]}",
        "content": base64.b64encode(
            json.dumps(record, indent=2, sort_keys=True).encode("utf-8")
        ).decode("ascii"),
        "branch": CACHE_REPO_BRANCH,
    }
    if prior_sha:
        body["sha"] = prior_sha
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.put(f"{CONTENTS_API}/{combo_path}", headers=headers, json=body, timeout=30)
    except requests.RequestException:
        return False
    return r.status_code in (200, 201)


def _live_nearby_search(
    api_key: str, lat: float, lng: float, radius: int, keyword: str, sleep_between_pages: float = 2.0
) -> list[dict]:
    """Hit Nearby Search live, exhausting pagination. Returns full results list."""
    out: list[dict] = []
    pagetoken: str | None = None
    while True:
        params: dict = {
            "location": f"{lat},{lng}",
            "radius": str(int(radius)),
            "keyword": keyword,
            "key": api_key,
        }
        if pagetoken:
            params["pagetoken"] = pagetoken
        try:
            r = requests.get(NEARBY_SEARCH_URL, params=params, timeout=45)
        except requests.RequestException as e:
            sys.stderr.write(f"places_cache: nearby live failed: {e}\n")
            return out
        if r.status_code != 200:
            sys.stderr.write(f"places_cache: nearby HTTP {r.status_code}: {r.text[:200]}\n")
            return out
        data = r.json()
        st = data.get("status")
        if st not in ("OK", "ZERO_RESULTS"):
            sys.stderr.write(f"places_cache: nearby status {st!r}: {data}\n")
            return out
        for res in data.get("results") or []:
            out.append(res)
        pagetoken = data.get("next_page_token")
        if not pagetoken:
            break
        time.sleep(max(2.0, sleep_between_pages))
    return out


def cached_nearby_search(
    api_key: str,
    lat: float,
    lng: float,
    radius_m: int,
    keyword: str,
    *,
    label: str = "",
    refresh: bool = False,
    sleep_between_pages: float = 2.0,
) -> tuple[list[dict], bool]:
    """Cache-aware Nearby Search.

    Returns ``(results, was_live)`` — ``was_live`` indicates whether this
    incarnation hit the live API (and was billed). Results are the raw
    Nearby Search response items from Google.

    On a cache hit the live call is skipped entirely; the cached
    ``results`` list is returned as-is. On a miss we hit the live API,
    write the response to the cache repo, and return.
    """
    combo = _coverage_path(keyword, lat, lng, radius_m)
    cached, sha = (None, None) if refresh else _fetch_coverage_record(combo)
    if cached and isinstance(cached.get("results"), list) and cached["results"]:
        return cached["results"], False
    # Treat empty-result records the same as a cached zero — they're a real
    # finding (the geography returned nothing for this keyword) and still
    # worth not re-paying for.
    if cached and "results" in cached:
        return cached.get("results") or [], False

    live = _live_nearby_search(
        api_key, lat, lng, radius_m, keyword, sleep_between_pages=sleep_between_pages
    )
    record = {
        "centroid": {"lat": lat, "lng": lng, "radius_m": int(radius_m)},
        "keyword": keyword,
        "label": label,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result_count": len(live),
        "results": live,
    }
    _write_coverage_record(combo, record, sha)
    return live, True


# ---- CLI for ad-hoc inspection ---------------------------------------------

def _cli(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="places_cache CLI — inspect or refresh a place_id")
    p.add_argument("place_id")
    p.add_argument("--tier", choices=["lite", "full"], default="full")
    p.add_argument("--refresh", action="store_true",
                   help="Bypass cache and re-fetch live; overwrite cached record.")
    p.add_argument("--key", default=None,
                   help="Google API key. Defaults to GOOGLE_MAPS_API_KEY / GOOGLE_PLACES_API_KEY.")
    args = p.parse_args(argv)

    api_key = args.key or os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        sys.stderr.write("No API key (set GOOGLE_MAPS_API_KEY or pass --key).\n")
        return 1
    fn = cached_place_details_lite if args.tier == "lite" else cached_place_details_full
    res = fn(api_key, args.place_id, refresh=args.refresh)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
