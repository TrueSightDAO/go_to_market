#!/usr/bin/env python3
"""
Hit List: detect retailers that **host circles** (women's circles, cacao ceremonies,
sound baths, breathwork, etc.) by crawling their **Website** for high-precision keywords.

Why this matters: 2026-04-28 observation — both Way Home Shop (just onboarded) and
Lumin Earth (existing partner) prominently host women's circles. Ceremonial cacao
genuinely lives in that ecosystem, so "hosts circles" is plausibly a leading
indicator of cacao sell-through. This script populates the **Hosts Circles** Hit
List column so we can later cross-reference against ``partners-velocity.json`` once
that has ≥4 weekly refreshes (see ``OPEN_FOLLOWUPS.md`` entry).

Output values written to **Hosts Circles**:
  - ``Yes`` (with matched keyword list, e.g. ``Yes (women's circle, sound bath)``) —
    at least one high-precision keyword matched on at least one fetched page.
  - ``Not detected`` — site fetched OK but no keyword matched. **NOT** equivalent to
    "doesn't host" — many retailers surface circles only on Instagram or newsletter,
    which this crawler does not reach.
  - empty / unset — row had no Website, or all fetches failed (treated as "not yet
    checked" so the next run can retry).

Idempotent: only writes rows whose **Hosts Circles** is currently empty unless ``--force``.

Environment:
  - ``google_credentials.json`` (Sheets editor on the Hit List workbook)
  - No external API keys required.

Usage:
  cd market_research
  python3 scripts/detect_circle_hosting_retailers.py --dry-run --limit 5
  python3 scripts/detect_circle_hosting_retailers.py --limit 200
  python3 scripts/detect_circle_hosting_retailers.py --force --limit 50  # re-check
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

REPO = Path(__file__).resolve().parents[1]
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HOSTS_CIRCLES_COL = "Hosts Circles"

KEYWORD_PATTERNS: tuple[tuple[str, str], ...] = (
    # (regex, canonical label written into the cell)
    (r"women'?s?\s+circle", "women's circle"),
    (r"moon\s+circle", "moon circle"),
    (r"new\s+moon\b", "new moon"),
    (r"full\s+moon\b", "full moon"),
    (r"cacao\s+ceremon", "cacao ceremony"),
    (r"cocoa\s+ceremon", "cocoa ceremony"),
    (r"sound\s+bath", "sound bath"),
    (r"sound\s+heal", "sound healing"),
    (r"breath\s*work", "breathwork"),
    (r"sister\s+circle", "sister circle"),
    (r"sacred\s+circle", "sacred circle"),
    (r"ecstatic\s+dance", "ecstatic dance"),
    (r"womb\s+heal", "womb healing"),
    (r"red\s+tent", "red tent"),
)

CRAWL_PATHS = ("/", "/events", "/classes", "/workshops", "/calendar", "/about", "/community")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; TrueSight CircleSniffer/0.1; +https://truesight.me)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def strip_tags(html: str) -> str:
    s = re.sub(r"(?is)<script.*?</script>", " ", html)
    s = re.sub(r"(?is)<style.*?</style>", " ", s)
    s = re.sub(r"(?is)<noscript.*?</noscript>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s)


def crawl_site(website: str, *, sleep_s: float, max_chars: int) -> tuple[bool, list[str]]:
    """Returns (any_page_fetched_ok, ordered_list_of_unique_canonical_keyword_labels)."""
    base = (website or "").strip()
    if not base:
        return False, []
    if not base.lower().startswith(("http://", "https://")):
        base = "https://" + base
    base = base.rstrip("/")

    fetched_ok = False
    found: list[str] = []
    seen: set[str] = set()

    for path in CRAWL_PATHS:
        url = base + "/" if path == "/" else base + path
        try:
            r = SESSION.get(url, timeout=20, allow_redirects=True)
        except requests.RequestException:
            time.sleep(sleep_s)
            continue
        if r.status_code != 200 or not r.text:
            time.sleep(sleep_s)
            continue
        ct = (r.headers.get("Content-Type") or "").lower()
        if "html" not in ct and "text" not in ct and "xml" not in ct:
            time.sleep(sleep_s)
            continue
        fetched_ok = True
        text = strip_tags(r.text)
        if len(text) > max_chars:
            text = text[:max_chars]
        for pat, label in KEYWORD_PATTERNS:
            if label in seen:
                continue
            if re.search(pat, text, flags=re.IGNORECASE):
                seen.add(label)
                found.append(label)
        time.sleep(sleep_s)

    return fetched_ok, found


def ensure_hosts_circles_column(ws: gspread.Worksheet, header: list[str], dry_run: bool) -> int:
    """Returns 0-based column index of Hosts Circles, adding the header if missing."""
    if HOSTS_CIRCLES_COL in header:
        return header.index(HOSTS_CIRCLES_COL)
    new_idx = len(header)
    if dry_run:
        print(f"[dry-run] would add header {HOSTS_CIRCLES_COL!r} at column {new_idx + 1}", flush=True)
        header.append(HOSTS_CIRCLES_COL)
        return new_idx
    if ws.col_count < new_idx + 1:
        ws.add_cols(new_idx + 1 - ws.col_count)
    ws.update_cell(1, new_idx + 1, HOSTS_CIRCLES_COL)
    header.append(HOSTS_CIRCLES_COL)
    print(f"Added header {HOSTS_CIRCLES_COL!r} at column {new_idx + 1}.", flush=True)
    return new_idx


def main() -> None:
    p = argparse.ArgumentParser(
        description="Detect circle-hosting retailers from their Website and write Hit List Hosts Circles column."
    )
    p.add_argument("--limit", type=int, default=200, help="Max rows to crawl this run (default 200).")
    p.add_argument("--dry-run", action="store_true", help="Print plan only; do not write the sheet.")
    p.add_argument("--force", action="store_true", help="Re-crawl rows whose Hosts Circles is already set.")
    p.add_argument("--sleep", type=float, default=0.4, help="Seconds between HTTP fetches.")
    p.add_argument("--sleep-write", type=float, default=0.3, help="Seconds between Sheets writes.")
    p.add_argument("--max-chars", type=int, default=80000, help="Per-page text truncation cap.")
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return
    header = [str(x or "").strip() for x in rows[0]]

    def col(name: str) -> int:
        if name not in header:
            raise SystemExit(f"Hit List missing required column {name!r}.")
        return header.index(name)

    i_shop = col("Shop Name")
    i_web = col("Website")
    i_hc = ensure_hosts_circles_column(ws, header, args.dry_run)

    queued: list[int] = []
    for ri, row in enumerate(rows[1:], start=2):
        cells = row + [""] * (len(header) - len(row))
        site = cells[i_web].strip()
        if not site:
            continue
        cur = cells[i_hc].strip() if i_hc < len(cells) else ""
        if cur and not args.force:
            continue
        queued.append(ri)
        if len(queued) >= max(1, args.limit):
            break

    print(
        f"Crawling {len(queued)} row(s). dry_run={args.dry_run} force={args.force}",
        flush=True,
    )

    yes_count = 0
    nd_count = 0
    skip_count = 0
    for ri in queued:
        cells = rows[ri - 1] + [""] * (len(header) - len(rows[ri - 1]))
        shop = cells[i_shop].strip()
        site = cells[i_web].strip()
        ok, hits = crawl_site(site, sleep_s=args.sleep, max_chars=args.max_chars)
        if not ok:
            print(f"  row {ri} {shop!r}: site unreachable — leaving blank for retry", flush=True)
            skip_count += 1
            continue
        if hits:
            value = f"Yes ({', '.join(hits)})"
            yes_count += 1
        else:
            value = "Not detected"
            nd_count += 1
        print(f"  row {ri} {shop!r}: {value}", flush=True)
        if not args.dry_run:
            ws.update(
                range_name=rowcol_to_a1(ri, i_hc + 1),
                values=[[value]],
                value_input_option="USER_ENTERED",
            )
            time.sleep(max(0.0, args.sleep_write))

    print(
        f"Done. yes={yes_count} not_detected={nd_count} unreachable_skip={skip_count} "
        f"dry_run={args.dry_run} force={args.force}",
        flush=True,
    )


if __name__ == "__main__":
    main()
