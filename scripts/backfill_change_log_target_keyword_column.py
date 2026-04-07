#!/usr/bin/env python3
"""
Ensure Change_log column J is **target_keyword** and fill it for rows whose url_or_path (col E)
matches known posts (Brazil/cocoa meta.json by default).

Existing workbooks created before this column may have only A:I. This script:
  1) Sets **Change_log!J1** to the header `target_keyword` if J1 is empty.
  2) For each data row with a URL matching `https://www.agroverse.shop/post/<slug>/`, writes the
     primary_keyword from meta into column J.

Usage (from market_research/):
  python3 scripts/backfill_change_log_target_keyword_column.py
  python3 scripts/backfill_change_log_target_keyword_column.py --dry-run

Requires google_credentials.json with Editor on the spreadsheet.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from google.oauth2.service_account import Credentials as SACredentials
from googleapiclient.discovery import build

from seo_workbook_append import SPREADSHEET_ID

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
_META = _REPO.parent / "agroverse_shop" / "scripts" / "brazil_cocoa_series" / "meta.json"

SHEET = "Change_log"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_POST_URL_RE = re.compile(
    r"https://www\.agroverse\.shop/post/([^/]+)/?", re.IGNORECASE
)


def _url_variants(slug: str) -> list[str]:
    base = f"https://www.agroverse.shop/post/{slug}"
    return [base + "/", base]


def _load_url_to_keyword() -> dict[str, str]:
    data = json.loads(_META.read_text(encoding="utf-8"))
    m: dict[str, str] = {}
    for p in data["posts"]:
        slug = p["slug"]
        kw = (p.get("primary_keyword") or "").strip()
        for u in _url_variants(slug):
            m[u] = kw
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not _SA_CREDS.is_file():
        raise SystemExit(f"Missing {_SA_CREDS}")
    if not _META.is_file():
        raise SystemExit(f"Missing {_META}")

    url_to_kw = _load_url_to_keyword()
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds)
    sh = svc.spreadsheets().values()

    res = sh.get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET}!A1:J1000",
    ).execute()
    rows = res.get("values") or []
    if not rows:
        print("No data in Change_log")
        return

    data_blocks: list[dict] = []

    # Header J1
    header = rows[0]
    j_header = header[9].strip() if len(header) > 9 else ""
    if not j_header or j_header.lower() != "target_keyword":
        data_blocks.append(
            {"range": f"{SHEET}!J1", "values": [["target_keyword"]]}
        )
        if args.dry_run:
            print("Would set J1 = target_keyword")

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 5:
            continue
        url = (row[4] or "").strip()
        mo = _POST_URL_RE.match(url)
        if not mo:
            continue
        slug = mo.group(1)
        kw = url_to_kw.get(url) or url_to_kw.get(url.rstrip("/") + "/")
        if not kw:
            for u in _url_variants(slug):
                if u in url_to_kw:
                    kw = url_to_kw[u]
                    break
        if not kw:
            continue
        existing_j = row[9].strip() if len(row) > 9 else ""
        if existing_j == kw:
            continue
        data_blocks.append({"range": f"{SHEET}!J{i}", "values": [[kw]]})
        if args.dry_run:
            print(f"Would set J{i} = {kw!r} for {url[:60]}...")

    if args.dry_run:
        print(f"Dry run: {len(data_blocks)} cell update(s)")
        return

    if not data_blocks:
        print("Nothing to update")
        return

    sh.batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"valueInputOption": "USER_ENTERED", "data": data_blocks},
    ).execute()
    print(f"Updated {len(data_blocks)} range(s) on {SHEET} (target_keyword)")


if __name__ == "__main__":
    main()
