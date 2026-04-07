#!/usr/bin/env python3
"""
Sync **DataForSEO_monthly_discovery** like Apps Script `monthlyDataForSeoKeywordDiscovery()`:

1. Obtain expanded keyword rows (live DataForSEO API **or** a local buyer-intent CSV).
2. Dedupe/sort by search_volume (higher first).
3. Drop keywords already listed on **Keywords_targets** column A.
4. Append up to 500 rows to **DataForSEO_monthly_discovery** with note
   `not in Keywords_targets`, or a placeholder row if there is nothing new.

Requires:
  - Live API: `market_research/.env`: DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD
  - CSV mode: no DataForSEO call (offline)
  - Always: `market_research/google_credentials.json` with Editor on the spreadsheet

Usage (from market_research/):
  python3 scripts/sync_dataforseo_monthly_discovery.py
  python3 scripts/sync_dataforseo_monthly_discovery.py --location-name "United States"
  python3 scripts/sync_dataforseo_monthly_discovery.py --use-latest-csv
  python3 scripts/sync_dataforseo_monthly_discovery.py --from-csv output/dataforseo/foo.csv
  python3 scripts/sync_dataforseo_monthly_discovery.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from dataforseo_buyer_intent_keywords import (
    DEFAULT_LOCATION_CODE,
    DEFAULT_SEEDS,
    dedupe_sort,
    fetch_keywords_for_keywords,
    load_credentials,
    rows_from_response,
)
from seo_workbook_append import SPREADSHEET_ID, append_rows, sheets_values

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "output" / "dataforseo"

_SH_KEYWORDS = "Keywords_targets"
_SH_MONTHLY = "DataForSEO_monthly_discovery"
_MAX_ROWS = 500


def _read_keywords_targets_col_a() -> set[str]:
    sv = sheets_values()
    res = sv.get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{_SH_KEYWORDS}!A2:A5000",
    ).execute()
    out: set[str] = set()
    for row in res.get("values") or []:
        if not row:
            continue
        k = (row[0] or "").strip().lower()
        if k:
            out.add(k)
    return out


def _str_cell(v) -> str:
    if v is None:
        return ""
    return str(v)


def _parse_volume(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _latest_buyer_intent_csv() -> Path | None:
    if not _OUT.is_dir():
        return None
    candidates = [
        p
        for p in _OUT.glob("buyer_intent_keywords_*.csv")
        if "excluded" not in p.name and "nonbrand" not in p.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _rows_from_csv(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kw = (row.get("keyword") or "").strip()
            if not kw:
                continue
            vol = _parse_volume(row.get("search_volume") or "")
            rows.append(
                {
                    "keyword": kw,
                    "search_volume": vol,
                    "competition": row.get("competition") or None,
                    "competition_index": row.get("competition_index") or None,
                    "cpc": row.get("cpc") or None,
                    "low_top_of_page_bid": row.get("low_top_of_page_bid") or None,
                    "high_top_of_page_bid": row.get("high_top_of_page_bid") or None,
                }
            )
    return dedupe_sort(rows)


def _rows_from_api(
    *,
    location_code: int | None,
    location_name: str | None,
    language_code: str,
    sort_by: str,
) -> list[dict]:
    login, password = load_credentials()
    print("Calling DataForSEO keywords_for_keywords (live)…", flush=True)
    data = fetch_keywords_for_keywords(
        login,
        password,
        DEFAULT_SEEDS[:20],
        location_code=location_code,
        location_name=location_name,
        language_code=language_code,
        sort_by=sort_by,
    )
    if data.get("status_code") != 20000:
        raise RuntimeError(
            f"DataForSEO API status_code={data.get('status_code')} "
            f"message={data.get('status_message')!r}"
        )
    print(f"API OK. tasks_cost≈{data.get('cost')}", flush=True)
    return dedupe_sort(rows_from_response(data))


def _build_sheet_rows(
    raw_rows: list[dict],
    active: set[str],
    pull_date: str,
    max_rows: int,
) -> list[list[str]]:
    to_write: list[list[str]] = []
    for row in raw_rows:
        if len(to_write) >= max_rows:
            break
        kw = (row.get("keyword") or "").strip()
        kl = kw.lower()
        if not kl or kl in active:
            continue
        to_write.append(
            [
                pull_date,
                kw,
                _str_cell(row.get("search_volume")),
                _str_cell(row.get("competition")),
                _str_cell(row.get("competition_index")),
                _str_cell(row.get("cpc")),
                _str_cell(row.get("low_top_of_page_bid")),
                _str_cell(row.get("high_top_of_page_bid")),
                "not in Keywords_targets",
            ]
        )
    return to_write


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--location-code", type=int, default=None)
    p.add_argument("--location-name", default=None)
    p.add_argument("--language-code", default="en")
    p.add_argument("--sort-by", default="search_volume")
    p.add_argument("--max-rows", type=int, default=_MAX_ROWS, dest="max_rows")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--use-latest-csv",
        action="store_true",
        help="Skip API; use newest buyer_intent_keywords_*.csv under output/dataforseo/",
    )
    p.add_argument("--from-csv", type=Path, default=None, help="Skip API; use this CSV path")
    args = p.parse_args()

    pull_date = date.today().isoformat()
    loc_code = args.location_code
    if args.location_name is None and loc_code is None:
        loc_code = DEFAULT_LOCATION_CODE

    if args.from_csv is not None and args.use_latest_csv:
        print("Use only one of --from-csv and --use-latest-csv", file=sys.stderr)
        raise SystemExit(2)

    raw_rows: list[dict]
    if args.from_csv is not None:
        cp = args.from_csv if args.from_csv.is_absolute() else _REPO / args.from_csv
        if not cp.is_file():
            print(f"CSV not found: {cp}", file=sys.stderr)
            raise SystemExit(1)
        print(f"Loading keywords from {cp}", flush=True)
        raw_rows = _rows_from_csv(cp)
    elif args.use_latest_csv:
        cp = _latest_buyer_intent_csv()
        if cp is None:
            print(
                "No buyer_intent_keywords_*.csv under output/dataforseo/. "
                "Run dataforseo_buyer_intent_keywords.py first or pass --from-csv.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(f"Loading keywords from {cp} (--use-latest-csv)", flush=True)
        raw_rows = _rows_from_csv(cp)
    else:
        try:
            raw_rows = _rows_from_api(
                location_code=loc_code,
                location_name=args.location_name,
                language_code=args.language_code,
                sort_by=args.sort_by,
            )
        except Exception as e:
            print(f"{e}", file=sys.stderr)
            latest = _latest_buyer_intent_csv()
            if latest:
                print(
                    f"Tip: DataForSEO blocked or failed; retry with:\n"
                    f"  python3 scripts/sync_dataforseo_monthly_discovery.py --use-latest-csv\n"
                    f"(uses {latest})",
                    file=sys.stderr,
                )
            raise SystemExit(1) from e

    active = _read_keywords_targets_col_a()
    print(f"Keywords_targets (col A): {len(active)} terms", flush=True)

    to_write = _build_sheet_rows(raw_rows, active, pull_date, args.max_rows)

    if args.dry_run:
        print(f"Dry-run: would append {len(to_write)} rows to {_SH_MONTHLY}")
        for r in to_write[:25]:
            print(f"  {r[1]!r} vol={r[2]}")
        if len(to_write) > 25:
            print(f"  ... +{len(to_write) - 25} more")
        return

    if not to_write:
        placeholder = [
            [
                pull_date,
                "(no new opportunities vs Keywords_targets)",
                "",
                "",
                "",
                "",
                "",
                "",
                "all ideas were already on Keywords_targets or API returned empty",
            ]
        ]
        append_rows(
            spreadsheet_id=SPREADSHEET_ID,
            sheet_title=_SH_MONTHLY,
            rows=placeholder,
        )
        print(f"Appended placeholder row to {_SH_MONTHLY} (no new keywords).")
        return

    append_rows(
        spreadsheet_id=SPREADSHEET_ID,
        sheet_title=_SH_MONTHLY,
        rows=to_write,
    )
    print(f"Appended {len(to_write)} rows to {_SH_MONTHLY}.")


if __name__ == "__main__":
    main()
