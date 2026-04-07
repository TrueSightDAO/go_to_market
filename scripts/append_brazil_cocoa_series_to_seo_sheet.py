#!/usr/bin/env python3
"""
Append Keywords_targets + Change_log rows for the Brazil / cocoa blog series.

Spreadsheet:
  https://docs.google.com/spreadsheets/d/1qRlufSUQusQbJc3AwonIvHtfiAQjwhnMtl79FFkGBt8/edit

Change_log convention: **one row per post** with **`target_keyword`** (column J) = `primary_keyword`
from `meta.json`. Shared helper: `seo_workbook_append.py`.

Usage (from market_research/):
  python3 scripts/append_brazil_cocoa_series_to_seo_sheet.py
  python3 scripts/append_brazil_cocoa_series_to_seo_sheet.py --date 2026-04-02
  python3 scripts/append_brazil_cocoa_series_to_seo_sheet.py --changelog-only
  python3 scripts/append_brazil_cocoa_series_to_seo_sheet.py --keywords-only
  python3 scripts/append_brazil_cocoa_series_to_seo_sheet.py --dry-run

Requires google_credentials.json (service account) with Editor on the spreadsheet.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from seo_workbook_append import SPREADSHEET_ID, append_rows, change_log_row

_REPO = Path(__file__).resolve().parent.parent
_META = _REPO.parent / "agroverse_shop" / "scripts" / "brazil_cocoa_series" / "meta.json"

SHEET_KEYWORDS = "Keywords_targets"
SHEET_CHANGELOG = "Change_log"

_SERIES_IMPACT = (
    "Brazil/cocoa non-brand cluster; internal links to farms/shipments; SERP-informed sections where added."
)
_REPO_REL_NOTE = (
    "Source: agroverse_shop/post/<slug>/index.html (fragments: "
    "agroverse_shop/scripts/brazil_cocoa_series/frags/; generator: "
    "agroverse_shop/scripts/generate_brazil_cocoa_seo_series.py)."
)


def _keyword_rows_from_meta(last_reviewed: str) -> list[list[str]]:
    data = json.loads(_META.read_text(encoding="utf-8"))
    rows: list[list[str]] = []
    for p in data["posts"]:
        kw = p.get("primary_keyword", "")
        url = f"https://www.agroverse.shop/post/{p['slug']}/"
        rows.append(
            [
                kw,
                p.get("intent_cluster", ""),
                p.get("priority", "P2"),
                url,
                p.get("sheet_notes", ""),
                "",
                "",
                "",
                "",
                last_reviewed,
            ]
        )
    return rows


def _changelog_rows(changed_date: str) -> list[list[str]]:
    data = json.loads(_META.read_text(encoding="utf-8"))
    rows: list[list[str]] = []
    for p in data["posts"]:
        slug = p["slug"]
        url = f"https://www.agroverse.shop/post/{slug}/"
        rel = f"agroverse_shop/post/{slug}/index.html"
        title = p.get("title", slug)
        summary = (
            f"Published blog post: {title}. Brazil/cocoa SEO series. {_REPO_REL_NOTE}"
        )
        rows.append(
            change_log_row(
                changed_date=changed_date,
                author="TrueSight Community",
                site_area="agroverse.shop blog",
                change_type="content_publish",
                url_or_path=url,
                summary=summary,
                link_pr_or_commit=rel,
                expected_impact=_SERIES_IMPACT,
                follow_up_date="",
                target_keyword=p.get("primary_keyword", ""),
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=None,
        help="changed_date for Change_log (default: today, local)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows; do not call the API",
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument(
        "--keywords-only",
        action="store_true",
        help="Append Keywords_targets only",
    )
    g.add_argument(
        "--changelog-only",
        action="store_true",
        help="Append Change_log only",
    )
    args = parser.parse_args()

    if not _META.is_file():
        raise SystemExit(f"Missing meta.json: {_META}")

    changed = args.date or date.today().isoformat()
    do_keywords = not args.changelog_only
    do_changelog = not args.keywords_only

    kw_rows = _keyword_rows_from_meta(changed) if do_keywords else []
    cl_rows = _changelog_rows(changed) if do_changelog else []

    if args.dry_run:
        if kw_rows:
            print("Keywords_targets (would append):")
            for r in kw_rows:
                print(r)
        if cl_rows:
            print("Change_log (would append), one row per URL:")
            for r in cl_rows:
                kw = r[9] if len(r) > 9 else ""
                print(r[0], kw, r[4], (r[5][:80] + "…") if len(r[5]) > 80 else r[5])
        return

    if kw_rows:
        append_rows(
            spreadsheet_id=SPREADSHEET_ID,
            sheet_title=SHEET_KEYWORDS,
            rows=kw_rows,
        )
        print(f"Appended {len(kw_rows)} rows to {SHEET_KEYWORDS}")
    if cl_rows:
        append_rows(
            spreadsheet_id=SPREADSHEET_ID,
            sheet_title=SHEET_CHANGELOG,
            rows=cl_rows,
        )
        print(f"Appended {len(cl_rows)} rows to {SHEET_CHANGELOG} (one per page)")


if __name__ == "__main__":
    main()
