#!/usr/bin/env python3
"""
Append chocolate-scoped keyword rows from the latest DataForSEO buyer-intent CSV to
**Keywords_targets** (skips keywords already present in column A).

Use after `scripts/dataforseo_buyer_intent_keywords.py` (or use an existing CSV in
`output/dataforseo/`). Optionally sync **DataForSEO_monthly_discovery** by running
Apps Script `monthlyDataForSeoKeywordDiscovery()` with updated seeds in Config.gs.

Usage (from market_research/):
  python3 scripts/append_chocolate_keywords_to_targets.py
  python3 scripts/append_chocolate_keywords_to_targets.py --csv output/dataforseo/foo.csv
  python3 scripts/append_chocolate_keywords_to_targets.py --dry-run

Requires google_credentials.json (Editor on the spreadsheet).
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

from seo_workbook_append import SPREADSHEET_ID, append_rows, sheets_values

_REPO = Path(__file__).resolve().parent.parent
_OUT = _REPO / "output" / "dataforseo"
_BLOCKLIST = _OUT / "brand_keyword_blocklist.txt"
_SHEET = "Keywords_targets"

# Linda / bar-launch adjacency: match DataForSEO-expanded queries we care about.
_CHOCOLATE_HINTS = (
    "chocolate",
    "bean to bar",
    "bean-to-bar",
    "bean2bar",
)


def _load_blocklist(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip().lower()
        if s:
            out.append(s)
    return out


def _is_blocked(keyword_lower: str, blocklist: list[str]) -> bool:
    return any(b in keyword_lower for b in blocklist)


def _is_chocolate_scope(keyword: str) -> bool:
    k = keyword.lower()
    return any(h in k for h in _CHOCOLATE_HINTS)


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


def _read_existing_keywords() -> set[str]:
    sv = sheets_values()
    res = (
        sv.get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{_SHEET}!A2:A5000",
        ).execute()
    )
    vals = res.get("values") or []
    out: set[str] = set()
    for row in vals:
        if not row:
            continue
        k = (row[0] or "").strip().lower()
        if k:
            out.add(k)
    return out


def _load_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            kw = (row.get("keyword") or "").strip()
            if kw:
                rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="Buyer-intent CSV path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    csv_path = args.csv or _latest_buyer_intent_csv()
    if csv_path is None or not csv_path.is_file():
        raise SystemExit(f"No CSV found. Run dataforseo_buyer_intent_keywords.py or pass --csv.")

    blocklist = _load_blocklist(_BLOCKLIST)
    existing = _read_existing_keywords()
    today = date.today().isoformat()
    intent = "Chocolate / bars & discovery"
    notes = (
        "DataForSEO buyer-intent expansion (chocolate scope). "
        "Single-estate dark bars roadmap — set target_url when PDP live."
    )

    raw = _load_csv_rows(csv_path)
    # Dedupe CSV by keyword (keep first / highest volume already sorted in file)
    seen: set[str] = set()
    to_append: list[list[str]] = []
    for row in raw:
        kw = (row.get("keyword") or "").strip()
        kl = kw.lower()
        if not kw or kl in seen:
            continue
        seen.add(kl)
        if not _is_chocolate_scope(kw):
            continue
        if _is_blocked(kl, blocklist):
            continue
        if kl in existing:
            continue

        vol = row.get("search_volume") or ""
        comp = row.get("competition") or ""
        cpc = row.get("cpc") or ""
        to_append.append(
            [
                kw,
                intent,
                "P2",
                "",
                notes,
                str(vol) if vol is not None else "",
                str(comp) if comp is not None else "",
                str(cpc) if cpc is not None else "",
                "",
                today,
            ]
        )

    # Highest search volume first (numeric when possible)
    def sort_key(r: list[str]):
        v = r[5]
        try:
            return -int(float(v))
        except (TypeError, ValueError):
            return 0

    to_append.sort(key=sort_key)

    print(f"CSV: {csv_path}")
    print(f"Existing Keywords_targets rows (col A scanned): {len(existing)}")
    print(f"New chocolate-scope rows to append: {len(to_append)}")
    if args.dry_run:
        for r in to_append[:40]:
            print(f"  {r[0]!r} vol={r[5]}")
        if len(to_append) > 40:
            print(f"  ... +{len(to_append) - 40} more")
        return

    if not to_append:
        print("Nothing to append (all chocolate rows already present or blocked).")
        return

    append_rows(
        spreadsheet_id=SPREADSHEET_ID,
        sheet_title=_SHEET,
        rows=to_append,
    )
    print(f"Appended {len(to_append)} rows to {_SHEET}.")


if __name__ == "__main__":
    main()
