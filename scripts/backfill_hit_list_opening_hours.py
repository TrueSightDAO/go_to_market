#!/usr/bin/env python3
"""
Backfill **Monday Open … Sunday Close** on the Hit List from Google Place Details.

1) **Notes contain ``place_id: …``** (discovery convention): Details + hour columns.

2) With **``--resolve-missing-place-id``**: rows **without** that token use **Find Place from Text**
   (shop name + address + city + state), biased by row **Latitude/Longitude** when present, to obtain
   a ``place_id``. The script appends ``place_id: …`` to **Notes**, then writes hours when Google
   returns ``opening_hours``.

Requires:
  - ``market_research/.env`` with ``GOOGLE_MAPS_API_KEY`` or ``GOOGLE_PLACES_API_KEY``
  - ``market_research/google_credentials.json`` (Editor on the Hit List workbook)

Usage:
  cd market_research
  python3 scripts/backfill_hit_list_opening_hours.py --dry-run --limit 20
  python3 scripts/backfill_hit_list_opening_hours.py --limit 200
  python3 scripts/backfill_hit_list_opening_hours.py --resolve-missing-place-id --dry-run --limit 15
  python3 scripts/backfill_hit_list_opening_hours.py --resolve-missing-place-id --limit 30 --find-radius-m 25000
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

import discover_apothecaries_la_hit_list as dl  # noqa: E402

PID_RE = re.compile(r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})")


def col_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        return -1


def cell_at(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def row_lat_lng(row: list[str], header: list[str]) -> tuple[float | None, float | None]:
    li = col_index(header, "Latitude")
    gi = col_index(header, "Longitude")
    if li < 0 or gi < 0:
        return None, None
    ls, gs = cell_at(row, li), cell_at(row, gi)
    if not ls or not gs:
        return None, None
    try:
        return float(ls), float(gs)
    except ValueError:
        return None, None


def build_find_query(row: list[str], header: list[str]) -> str | None:
    name = cell_at(row, col_index(header, "Shop Name"))
    if not name:
        return None
    addr = cell_at(row, col_index(header, "Address"))
    city = cell_at(row, col_index(header, "City"))
    state = cell_at(row, col_index(header, "State"))
    parts = [name]
    if addr:
        parts.append(addr)
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if len(parts) == 1 and not city and not state and not addr:
        return name
    return ", ".join(parts)


def append_place_id_to_notes(notes: str, pid: str) -> str:
    """Append a dedupe-friendly ``place_id:`` line without removing existing text."""
    raw = notes or ""
    if PID_RE.search(raw):
        return raw
    tag = f"place_id: {pid}"
    tail = f"{tag} (auto-resolved from shop name/address)."
    stripped = raw.rstrip()
    if not stripped:
        return tail
    return f"{stripped}\n{tail}"


def resolve_place_id(
    key: str,
    row: list[str],
    header: list[str],
    *,
    radius_m: float,
) -> tuple[str | None, str]:
    q = build_find_query(row, header)
    if not q:
        return None, "missing_query"
    lat, lng = row_lat_lng(row, header)
    try:
        data = dl.find_place_from_text(key, q, lat, lng, radius_m=radius_m)
    except Exception as exc:
        return None, f"find_place_error:{exc}"
    st = data.get("status") or ""
    if st != "OK":
        return None, f"find_place_{st}"
    cands = data.get("candidates") or []
    if not cands:
        return None, "zero_results"
    pid = (cands[0].get("place_id") or "").strip()
    if not pid:
        return None, "empty_place_id"
    return pid, "ok"


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill Hit List opening hour columns from Places.")
    p.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max Hit List rows that receive an opening-hours write (or dry-run preview) this run. "
        "Note-only appends from --resolve-missing-place-id do not count toward this cap.",
    )
    p.add_argument("--sleep-details", type=float, default=0.08, help="Seconds between Places API calls.")
    p.add_argument(
        "--sleep-write",
        type=float,
        default=1.2,
        help="Seconds after each sheet write batch (reduces Sheets write 429s). Default 1.2.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Update hour columns even if some weekday cells are already non-empty.",
    )
    p.add_argument(
        "--resolve-missing-place-id",
        action="store_true",
        help="Use Find Place from Text when Notes has no place_id (needs Shop Name + some location text).",
    )
    p.add_argument(
        "--find-radius-m",
        type=float,
        default=50000.0,
        help="locationbias circle radius in meters when row has lat/lng (default 50000).",
    )
    p.add_argument("--dry-run", action="store_true", help="Print actions only; do not write the sheet.")
    args = p.parse_args()

    key = dl.maps_api_key()
    gc = dl.gspread_client()
    ws = gc.open_by_key(dl.SPREADSHEET_ID).worksheet(dl.HIT_LIST_WS)
    rows = ws.get_all_values()
    if len(rows) < 2:
        print("Hit List has no data rows.", flush=True)
        return
    header = [str(x or "").strip() for x in rows[0]]

    missing_any_header = [h for h in dl.HIT_LIST_OPENING_HOUR_COLS if h not in header]
    if missing_any_header:
        raise SystemExit(
            "Hit List row 1 is missing hour column(s): "
            + ", ".join(missing_any_header)
            + ". Add these headers on row 1 (after Contact Form URL), then re-run."
        )

    idx_notes = col_index(header, "Notes")
    if idx_notes < 0:
        raise SystemExit('Hit List must have a "Notes" column.')

    hour_indices = [col_index(header, h) for h in dl.HIT_LIST_OPENING_HOUR_COLS]
    if any(i < 0 for i in hour_indices):
        raise SystemExit("Could not resolve all hour column indices from row 1.")

    hour_rows_updated = 0
    skipped = 0
    resolved_notes = 0

    for r_idx, row in enumerate(rows[1:], start=2):
        if hour_rows_updated >= args.limit:
            break
        notes = row[idx_notes] if idx_notes < len(row) else ""

        def cell(ci: int) -> str:
            return (row[ci] if ci < len(row) else "").strip()

        has_any_hours = any(cell(ci) for ci in hour_indices)
        if has_any_hours and not args.force:
            skipped += 1
            continue

        m = PID_RE.search(notes or "")
        pid: str | None = m.group(1).strip() if m else None
        resolve_reason = ""

        if not pid and args.resolve_missing_place_id:
            q = build_find_query(row, header)
            if not q:
                skipped += 1
                continue
            pid, resolve_reason = resolve_place_id(key, row, header, radius_m=args.find_radius_m)
            time.sleep(max(0.0, args.sleep_details))
            if not pid:
                print(f"Row {r_idx}: could not resolve place_id ({resolve_reason}) query={q!r}", flush=True)
                skipped += 1
                continue
            new_notes = append_place_id_to_notes(notes, pid)
            if new_notes != (notes or "") and not args.dry_run:
                ncell = rowcol_to_a1(r_idx, idx_notes + 1)
                ws.update(range_name=ncell, values=[[new_notes]], value_input_option="USER_ENTERED")
                notes = new_notes
                resolved_notes += 1
                print(f"Row {r_idx}: appended place_id to Notes ({pid})", flush=True)
                time.sleep(max(0.0, args.sleep_write))
            elif new_notes != (notes or "") and args.dry_run:
                print(f"Row {r_idx}: dry-run would append place_id to Notes ({pid}) query={q!r}", flush=True)
        elif not pid:
            skipped += 1
            continue

        assert pid is not None

        det = dl.place_details(key, pid)
        time.sleep(max(0.0, args.sleep_details))
        if det.get("status") != "OK":
            print(f"Row {r_idx}: Details not OK for place_id={pid!r}", flush=True)
            skipped += 1
            continue
        res = det.get("result") or {}
        grid = dl.opening_hours_week_grid_from_place_result(res)
        if not any((grid.get(h) or "").strip() for h in dl.HIT_LIST_OPENING_HOUR_COLS):
            print(f"Row {r_idx}: no opening_hours for place_id={pid!r}", flush=True)
            skipped += 1
            continue

        if args.dry_run:
            name = cell_at(row, col_index(header, "Shop Name"))
            print(f"Row {r_idx}: dry-run would update hours for {name!r} ({pid})", flush=True)
            hour_rows_updated += 1
            continue

        ci0 = hour_indices[0]
        contiguous = hour_indices == list(range(ci0, ci0 + len(hour_indices)))
        vals = [[(grid.get(h) or "").strip() for h in dl.HIT_LIST_OPENING_HOUR_COLS]]
        if contiguous:
            rng = f"{rowcol_to_a1(r_idx, ci0 + 1)}:{rowcol_to_a1(r_idx, hour_indices[-1] + 1)}"
            ws.update(range_name=rng, values=vals, value_input_option="USER_ENTERED")
        else:
            for h in dl.HIT_LIST_OPENING_HOUR_COLS:
                ci = col_index(header, h)
                val = (grid.get(h) or "").strip()
                cell_a1 = rowcol_to_a1(r_idx, ci + 1)
                ws.update(range_name=cell_a1, values=[[val]], value_input_option="USER_ENTERED")

        print(f"Row {r_idx}: updated hours for place_id={pid}", flush=True)
        hour_rows_updated += 1
        time.sleep(max(0.0, args.sleep_write))

    print(
        f"Done. hour_rows_updated={hour_rows_updated} notes_place_id_appended={resolved_notes} "
        f"skipped={skipped} dry_run={args.dry_run} resolve={bool(args.resolve_missing_place_id)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
