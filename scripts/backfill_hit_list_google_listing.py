#!/usr/bin/env python3
"""
Backfill the Hit List **Google listing** column from Google Place Details ``business_status``.

- **Closed** → ``CLOSED_PERMANENTLY``
- **Temporarily closed** → ``CLOSED_TEMPORARILY``
- Empty → operational or unknown

Requires ``place_id`` in **Notes** (same convention as other Hit List scripts), unless
``--resolve-missing-place-id`` is used (shares Find Place logic with opening-hours backfill).

Usage:
  cd market_research
  python3 scripts/backfill_hit_list_google_listing.py --dry-run --limit 50
  python3 scripts/backfill_hit_list_google_listing.py --limit 500 --sleep-write 1.2
  python3 scripts/backfill_hit_list_google_listing.py --resolve-missing-place-id --limit 200
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from gspread.utils import rowcol_to_a1

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import backfill_hit_list_opening_hours as bl  # noqa: E402
import discover_apothecaries_la_hit_list as dl  # noqa: E402

PID_RE = re.compile(r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})")


def col_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill Hit List Google listing from Places business_status.")
    p.add_argument("--limit", type=int, default=500, help="Max rows updated this run.")
    p.add_argument("--sleep-details", type=float, default=0.08, help="Seconds between Place Details calls.")
    p.add_argument(
        "--sleep-write",
        type=float,
        default=1.2,
        help="Seconds after each sheet write (reduces 429s). Default 1.2.",
    )
    p.add_argument("--force", action="store_true", help="Overwrite non-empty Google listing cells.")
    p.add_argument(
        "--resolve-missing-place-id",
        action="store_true",
        help="Use Find Place from Text when Notes has no place_id.",
    )
    p.add_argument("--find-radius-m", type=float, default=50000.0, help="Find Place locationbias radius (m).")
    p.add_argument("--dry-run", action="store_true", help="Do not write the sheet.")
    args = p.parse_args()

    key = dl.maps_api_key()
    gc = dl.gspread_client()
    ws = gc.open_by_key(dl.SPREADSHEET_ID).worksheet(dl.HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Hit List has no data rows.", flush=True)
        return

    header = [str(x or "").strip() for x in rows[0]]
    if dl.GOOGLE_LISTING_COL not in header:
        c = len(header) + 1
        if not args.dry_run:
            if ws.col_count < c:
                ws.add_cols(c - ws.col_count)
            ws.update_cell(1, c, dl.GOOGLE_LISTING_COL)
            time.sleep(max(0.0, args.sleep_write))
        header.append(dl.GOOGLE_LISTING_COL)
        print(f"Added header {dl.GOOGLE_LISTING_COL!r} at column {c}.", flush=True)

    idx_notes = col_index(header, "Notes")
    idx_gl = col_index(header, dl.GOOGLE_LISTING_COL)
    if idx_notes < 0 or idx_gl < 0:
        raise SystemExit("Hit List must have Notes and Google listing columns.")

    updated = 0
    skipped = 0
    notes_appended = 0

    for r_idx, row in enumerate(rows[1:], start=2):
        if updated >= args.limit:
            break

        notes = row[idx_notes] if idx_notes < len(row) else ""
        cur = (row[idx_gl] if idx_gl < len(row) else "").strip()
        if cur and not args.force:
            skipped += 1
            continue

        m = PID_RE.search(notes or "")
        pid: str | None = m.group(1).strip() if m else None

        if not pid and args.resolve_missing_place_id:
            q = bl.build_find_query(row, header)
            if not q:
                skipped += 1
                continue
            pid, reason = bl.resolve_place_id(key, row, header, radius_m=args.find_radius_m)
            time.sleep(max(0.0, args.sleep_details))
            if not pid:
                print(f"Row {r_idx}: could not resolve place_id ({reason}) query={q!r}", flush=True)
                skipped += 1
                continue
            new_notes = bl.append_place_id_to_notes(notes, pid)
            if new_notes != (notes or "") and not args.dry_run:
                ncell = rowcol_to_a1(r_idx, idx_notes + 1)
                ws.update(range_name=ncell, values=[[new_notes]], value_input_option="USER_ENTERED")
                notes = new_notes
                notes_appended += 1
                print(f"Row {r_idx}: appended place_id to Notes ({pid})", flush=True)
                time.sleep(max(0.0, args.sleep_write))
            elif new_notes != (notes or "") and args.dry_run:
                print(f"Row {r_idx}: dry-run would append place_id ({pid})", flush=True)
        elif not pid:
            skipped += 1
            continue

        det = dl.place_details(key, pid)
        time.sleep(max(0.0, args.sleep_details))
        if det.get("status") != "OK":
            print(f"Row {r_idx}: Details not OK for place_id={pid!r}", flush=True)
            skipped += 1
            continue

        res = det.get("result") or {}
        label = dl.google_listing_from_business_status(res.get("business_status"))

        if args.dry_run:
            print(f"Row {r_idx}: dry-run would set Google listing={label!r} ({pid})", flush=True)
            updated += 1
            continue

        cell = rowcol_to_a1(r_idx, idx_gl + 1)
        ws.update(range_name=cell, values=[[label]], value_input_option="USER_ENTERED")
        print(f"Row {r_idx}: Google listing={label!r} ({pid})", flush=True)
        updated += 1
        time.sleep(max(0.0, args.sleep_write))

    print(
        f"Done. rows_updated={updated} notes_place_id_appended={notes_appended} "
        f"skipped={skipped} dry_run={args.dry_run}",
        flush=True,
    )


if __name__ == "__main__":
    main()
