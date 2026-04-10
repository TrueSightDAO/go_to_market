#!/usr/bin/env python3
"""
Report duplicate or near-duplicate rows on the Hit List tab.

Uses the same dedupe signals as discover_apothecaries_la_hit_list.py:
  - repeated place_id in Notes
  - repeated Store Key
  - same slug(name) + Latitude/Longitude rounded to 4 decimals
  - same normalized Shop Name + Address (columns A + D)

Examples:
  cd market_research
  python3 scripts/hit_list_report_duplicates.py
  python3 scripts/hit_list_report_duplicates.py --min-rows 2
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from discover_apothecaries_la_hit_list import (  # noqa: E402
    SPREADSHEET_ID,
    HIT_LIST_WS,
    compute_store_key,
    compute_store_key_legacy,
    geo_name_fingerprint,
    gspread_client,
    name_address_fingerprint,
)


def col_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def main() -> None:
    p = argparse.ArgumentParser(description="List duplicate Hit List rows (read-only).")
    p.add_argument(
        "--min-rows",
        type=int,
        default=2,
        metavar="N",
        help="Only print groups with at least this many rows (default: 2).",
    )
    args = p.parse_args()

    gc = gspread_client()
    ws = gc.open_by_key(SPREADSHEET_ID).worksheet(HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Hit List is empty.")
        return

    header = rows[0]
    def cell(row: list[str], i: int) -> str:
        if i < 0 or i >= len(row):
            return ""
        return row[i]

    ni = col_index(header, "Notes")
    ski = col_index(header, "Store Key")
    name_i = col_index(header, "Shop Name")
    addr_i = col_index(header, "Address")
    city_i = col_index(header, "City")
    state_i = col_index(header, "State")
    lat_i = col_index(header, "Latitude")
    lng_i = col_index(header, "Longitude")

    pid_re = re.compile(r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})")

    by_place_id: dict[str, list[int]] = defaultdict(list)
    by_store_key: dict[str, list[int]] = defaultdict(list)
    by_geo_name: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    by_name_addr: dict[tuple[str, str], list[int]] = defaultdict(list)

    for ridx, row in enumerate(rows[1:], start=2):
        notes = cell(row, ni)
        for m in pid_re.finditer(notes):
            by_place_id[m.group(1).strip()].append(ridx)

        sk = cell(row, ski).strip()
        if sk:
            by_store_key[sk].append(ridx)

        name = cell(row, name_i).strip()
        street = cell(row, addr_i).strip()
        city = cell(row, city_i).strip()
        state = cell(row, state_i).strip()
        if name:
            by_store_key[compute_store_key(name, street, city, state)].append(ridx)
            by_store_key[compute_store_key_legacy(name, street, city, state)].append(ridx)

        try:
            la = float(cell(row, lat_i)) if cell(row, lat_i).strip() else None
            ln = float(cell(row, lng_i)) if cell(row, lng_i).strip() else None
        except ValueError:
            la, ln = None, None
        gfp = geo_name_fingerprint(name, la, ln)
        if gfp:
            by_geo_name[gfp].append(ridx)

        na = name_address_fingerprint(name, street)
        if na:
            by_name_addr[na].append(ridx)

    def dedupe_row_lists(groups: dict[str | tuple, list[int]]) -> dict[str | tuple, list[int]]:
        out: dict[str | tuple, list[int]] = {}
        for k, lst in groups.items():
            uniq = sorted(set(lst))
            if len(uniq) >= args.min_rows:
                out[k] = uniq
        return out

    # de-dupe row index lists inside each bucket
    pid_dups = {k: v for k, v in by_place_id.items() if len(set(v)) >= args.min_rows}
    # store key: same row may appear multiple times via computed keys; uniq per key
    sk_dups = dedupe_row_lists(by_store_key)
    geo_dups = dedupe_row_lists(by_geo_name)
    name_addr_dups = dedupe_row_lists(by_name_addr)

    print(f"Hit List sheet rows: {len(rows) - 1} (data), spreadsheet: {SPREADSHEET_ID!r}\n")

    if pid_dups:
        print("--- Duplicate place_id in Notes ---")
        for pid in sorted(pid_dups):
            rs = sorted(set(pid_dups[pid]))
            print(f"  {pid}: rows {rs}")
        print()
    else:
        print("--- Duplicate place_id in Notes: none ---\n")

    if sk_dups:
        print("--- Duplicate Store Key (column or computed) ---")
        for sk in sorted(sk_dups, key=lambda x: (len(sk_dups[x]), str(x)), reverse=True)[:80]:
            rs = sk_dups[sk]
            if len(rs) < args.min_rows:
                continue
            print(f"  {sk!r}: rows {rs}")
        if len(sk_dups) > 80:
            print(f"  ... ({len(sk_dups)} keys total, truncated to 80)")
        print()
    else:
        print("--- Duplicate Store Key: none ---\n")

    if geo_dups:
        print("--- Same name slug + lat/lng (4 decimals) ---")
        for gfp in sorted(geo_dups, key=lambda x: len(geo_dups[x]), reverse=True)[:80]:
            rs = geo_dups[gfp]
            if len(rs) < args.min_rows:
                continue
            print(f"  {gfp!r}: rows {rs}")
        if len(geo_dups) > 80:
            print(f"  ... ({len(geo_dups)} groups total, truncated to 80)")
        print()
    else:
        print("--- Same name+geo fingerprint: none ---\n")

    if name_addr_dups:
        print("--- Same normalized Shop Name + Address (A + D) ---")
        for fp in sorted(name_addr_dups, key=lambda x: len(name_addr_dups[x]), reverse=True)[:80]:
            rs = name_addr_dups[fp]
            if len(rs) < args.min_rows:
                continue
            print(f"  {fp!r}: rows {rs}")
        if len(name_addr_dups) > 80:
            print(f"  ... ({len(name_addr_dups)} groups total, truncated to 80)")
        print()
    else:
        print("--- Same name+address (A+D): none ---\n")


if __name__ == "__main__":
    main()
