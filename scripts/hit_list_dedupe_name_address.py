#!/usr/bin/env python3
"""
Remove duplicate Hit List rows with the same normalized **Shop Name** (A) and **Address** (D).

Uses ``name_address_fingerprint`` from ``discover_apothecaries_la_hit_list.py`` (same as
discovery dedupe). For each duplicate group, **keeps the lowest row number** (first row
in the sheet = oldest insert for append-only history) and **deletes** higher rows.

Default is **dry-run** (print plan only). Pass ``--apply`` to delete rows (descending order
so row indices stay valid).

Examples:
  cd market_research
  python3 scripts/hit_list_dedupe_name_address.py
  python3 scripts/hit_list_dedupe_name_address.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from discover_apothecaries_la_hit_list import (  # noqa: E402
    HIT_LIST_WS,
    SPREADSHEET_ID,
    gspread_client,
    name_address_fingerprint,
)
from hit_list_dapp_remarks_sheet import gspread_retry  # noqa: E402


def col_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def cell(row: list[str], i: int) -> str:
    if i < 0 or i >= len(row):
        return ""
    return row[i]


def main() -> None:
    p = argparse.ArgumentParser(
        description="Dedupe Hit List by normalized Shop Name + Address; keep oldest row."
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Delete duplicate rows (default: print plan only).",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=0.35,
        help="Seconds between delete_rows calls when applying (default 0.35).",
    )
    args = p.parse_args()

    gc = gspread_client()
    ws = gspread_retry(lambda: gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS))
    rows = gspread_retry(lambda: ws.get_all_values())
    if len(rows) < 2:
        print("Hit List is empty.")
        return

    header = rows[0]
    name_i = col_index(header, "Shop Name")
    addr_i = col_index(header, "Address")
    if name_i < 0 or addr_i < 0:
        raise SystemExit('Hit List must have "Shop Name" and "Address" columns.')

    by_fp: dict[tuple[str, str], list[int]] = defaultdict(list)
    for ridx, row in enumerate(rows[1:], start=2):
        name = cell(row, name_i).strip()
        street = cell(row, addr_i).strip()
        fp = name_address_fingerprint(name, street)
        if fp:
            by_fp[fp].append(ridx)

    to_delete: list[int] = []
    for fp, rlist in sorted(by_fp.items(), key=lambda x: (-len(x[1]), str(x[0]))):
        uniq = sorted(set(rlist))
        if len(uniq) < 2:
            continue
        keep = uniq[0]
        drop = uniq[1:]
        to_delete.extend(drop)
        print(f"{fp!r}\n  keep row {keep}, delete rows {drop}")

    if not to_delete:
        print("No duplicate name+address groups found.")
        return

    to_delete_sorted = sorted(set(to_delete), reverse=True)
    print(
        f"\nSpreadsheet {SPREADSHEET_ID!r}, tab {HIT_LIST_WS!r}: "
        f"{len(to_delete_sorted)} row(s) to delete (after dedupe)."
    )

    if not args.apply:
        print("Dry-run only. Re-run with --apply to delete these rows.")
        return

    for r in to_delete_sorted:
        gspread_retry(lambda row=r: ws.delete_rows(row))
        time.sleep(max(0.0, args.sleep))
    print(f"Deleted {len(to_delete_sorted)} row(s).")


if __name__ == "__main__":
    main()
