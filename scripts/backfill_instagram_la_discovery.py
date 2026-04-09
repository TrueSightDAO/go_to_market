#!/usr/bin/env python3
"""
Fill **Instagram** on Hit List rows created by `discover_apothecaries_la_hit_list.py`
(Notes contain "Auto-discovered (Google Places Nearby") when Instagram is empty.

Strategy:
  1. If **Website** is set, fetch the page and extract instagram.com/{handle} links.
  2. Else if **place_id** is in Notes, refresh Place Details for **website**, then (1).
  3. Optional fallback: DuckDuckGo HTML search for "{shop} {city} instagram" and scan for
     instagram.com links (rate-limited).

Instagram column is written as **@handle** (no URL) to match typical CRM / teammate skim.

Usage:
  cd market_research
  python3 scripts/backfill_instagram_la_discovery.py --dry-run
  python3 scripts/backfill_instagram_la_discovery.py --limit 10
  python3 scripts/backfill_instagram_la_discovery.py
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.parse
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

DISCOVERY_NOTE_SNIPPET = "Auto-discovered (Google Places Nearby"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

# Reserved Instagram path segments — not profile handles
IG_RESERVED = frozenset(
    {
        "p",
        "reel",
        "reels",
        "stories",
        "explore",
        "accounts",
        "direct",
        "tv",
        "legal",
        "about-us",
        "api",
        "developer",
    }
)

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)

# instagram.com/{handle} — protocol-relative and https; stop before next path/query.
IG_HREF_RE = re.compile(
    r"(?:https?:)?//(?:www\.)?instagram\.com/([A-Za-z0-9._]{1,30})(?:/[?\s\"'&<>]|$)",
    re.IGNORECASE,
)

PLACE_ID_IN_NOTES = re.compile(
    r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})",
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
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except ImportError:
        pass


def maps_api_key() -> str | None:
    load_dotenv_repo()
    return os.environ.get("GOOGLE_MAPS_API_KEY") or os.environ.get("GOOGLE_PLACES_API_KEY")


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def place_details_website(key: str, place_id: str) -> str:
    fields = "website"
    r = requests.get(
        DETAILS_URL,
        params={"place_id": place_id, "fields": fields, "key": key},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        return ""
    return ((data.get("result") or {}).get("website") or "").strip()


def normalize_ig_handle(raw: str) -> str | None:
    h = raw.strip().strip("/").split("?")[0].split("/")[0]
    if not h or len(h) < 2:
        return None
    if h.lower() in IG_RESERVED:
        return None
    if not re.match(r"^[A-Za-z0-9._]+$", h):
        return None
    return h


def extract_handles_from_html(html: str) -> list[str]:
    found: list[str] = []
    patterns = (
        IG_HREF_RE,
        # Shopify / marketing emails: "instagram.com/handle" without scheme
        re.compile(
            r"(?<![\w])instagram\.com/([A-Za-z0-9._]{1,30})(?:[^a-zA-Z0-9._?#]|$)",
            re.IGNORECASE,
        ),
    )
    for rx in patterns:
        for m in rx.finditer(html):
            h = normalize_ig_handle(m.group(1))
            if h:
                found.append(h)
    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for h in found:
        kl = h.lower()
        if kl in seen:
            continue
        seen.add(kl)
        out.append(h)
    return out


def fetch_html(url: str, timeout: float = 15.0) -> str | None:
    u = url.strip()
    if not u:
        return None
    if not u.lower().startswith(("http://", "https://")):
        u = "https://" + u
    try:
        r = SESSION.get(u, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return None
        ct = (r.headers.get("Content-Type") or "").lower()
        if "text" not in ct and "html" not in ct and "xml" not in ct:
            # Still try; some servers omit Content-Type
            pass
        return r.text if r.text else None
    except requests.RequestException:
        return None


def instagram_from_website(website: str, sleep_after: float) -> str | None:
    html = fetch_html(website)
    time.sleep(max(0.0, sleep_after))
    if not html:
        return None
    handles = extract_handles_from_html(html)
    return handles[0] if handles else None


def ddg_find_instagram(shop: str, city: str, sleep_after: float) -> str | None:
    """Lightweight HTML scrape; best-effort only."""
    q = f"{shop} {city} instagram".strip()
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    try:
        r = SESSION.get(url, timeout=20)
        time.sleep(max(0.0, sleep_after))
        if r.status_code != 200 or not r.text:
            return None
        handles = extract_handles_from_html(r.text)
        return handles[0] if handles else None
    except requests.RequestException:
        time.sleep(max(0.0, sleep_after))
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill Instagram for LA Places discovery rows.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = all).")
    p.add_argument("--sleep", type=float, default=0.35, help="Delay between HTTP fetches.")
    p.add_argument(
        "--ddg",
        action="store_true",
        help="If website scan finds nothing, try DuckDuckGo HTML search (slower).",
    )
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows")
        return
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    need = ["Shop Name", "City", "Website", "Instagram", "Notes"]
    for n in need:
        if n not in idx:
            raise SystemExit(f"Hit List missing column {n!r}")

    i_name = idx["Shop Name"]
    i_city = idx["City"]
    i_web = idx["Website"]
    i_ig = idx["Instagram"]
    i_notes = idx["Notes"]
    col_ig_1based = i_ig + 1

    mkey = maps_api_key()
    processed = 0
    updated = 0

    for rn, row in enumerate(rows[1:], start=2):
        if args.limit and processed >= args.limit:
            break
        cells = row + [""] * (len(header) - len(row))
        notes = cells[i_notes].strip()
        if DISCOVERY_NOTE_SNIPPET not in notes:
            continue
        ig_existing = cells[i_ig].strip()
        if ig_existing:
            continue

        shop = cells[i_name].strip()
        if not shop:
            continue

        city = cells[i_city].strip()
        website = cells[i_web].strip()
        place_m = PLACE_ID_IN_NOTES.search(notes)
        place_id = place_m.group(1) if place_m else ""

        processed += 1
        handle: str | None = None

        if website:
            handle = instagram_from_website(website, args.sleep)

        if not handle and place_id and mkey:
            try:
                w2 = place_details_website(mkey, place_id)
                time.sleep(max(0.0, args.sleep))
                if w2 and w2.strip() != website:
                    handle = instagram_from_website(w2.strip(), args.sleep)
                elif w2 and not website:
                    handle = instagram_from_website(w2.strip(), args.sleep)
            except requests.RequestException as e:
                print(f"  [{shop}] Places details error: {e}", flush=True)

        if not handle and args.ddg:
            handle = ddg_find_instagram(shop, city or "Los Angeles", args.sleep * 2)

        if not handle:
            print(f"  [{shop}] — no Instagram found", flush=True)
            continue

        at = f"@{handle}"
        if args.dry_run:
            print(f"  [{shop}] -> {at} (row {rn})")
        else:
            ws.update_cell(rn, col_ig_1based, at)
            print(f"  [{shop}] -> {at} (row {rn})", flush=True)
            time.sleep(0.25)
        updated += 1

    print(f"Done. Candidates processed: {processed}, Instagram filled: {updated}.")


if __name__ == "__main__":
    main()
