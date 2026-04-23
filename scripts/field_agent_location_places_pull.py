#!/usr/bin/env python3
"""
Process **Recent Field Agent Location** rows (Status=pending) for the holistic wellness Hit List:

- If another row was already **pulled** within **dedupe miles / hours** (defaults: 20 mi, 24 h;
  tunable via ``--dedupe-miles`` / ``--dedupe-hours``, or disabled with ``--no-recent-dedupe``),
  mark this row **ignored because already pulled** and **do not** call Google Places Nearby.
- Otherwise run **Places Nearby Search** around the agent lat/lng, enrich with Place Details,
  dedupe against the live **Hit List**, append new **Research** rows, set Status **pulled**.
  After appends, writes **AU** / **AV** COUNTIFS formulas (same as ``set_hit_list_warmup_touches_formula.py``)
  so warm-up / follow-up **sent** counts resolve from **Email Agent Follow Up**.

Also appends an audit row to **DApp Remarks** (Processed=Yes) summarizing each agent row handled.

Requires:
  - market_research/google_credentials.json (Sheets editor on the workbook)
  - GOOGLE_MAPS_API_KEY or GOOGLE_PLACES_API_KEY in .env (server/IP key; not browser-restricted)

Usage:
  cd market_research
  python3 scripts/field_agent_location_places_pull.py --dry-run --limit 3
  python3 scripts/field_agent_location_places_pull.py --limit 5
  # Fast travel: only skip if a prior pull was very close in space/time (Hit List dedupe unchanged):
  python3 scripts/field_agent_location_places_pull.py --dedupe-miles 8 --dedupe-hours 2 --limit 20
  python3 scripts/field_agent_location_places_pull.py --no-recent-dedupe --limit 20
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import gspread
from gspread.utils import rowcol_to_a1

# Reuse Places + Hit List helpers from the apothecary discovery script (same spreadsheet).
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import discover_apothecaries_la_hit_list as dl  # noqa: E402

from hit_list_dapp_remarks_sheet import (  # noqa: E402
    _parse_row_from_append_response,
    gspread_retry,
)
from set_hit_list_warmup_touches_formula import write_au_av_for_hit_list_rows  # noqa: E402

SPREADSHEET_ID = dl.SPREADSHEET_ID
HIT_LIST_NAME = dl.HIT_LIST_WS
RECENT_SHEET_NAME = "Recent Field Agent Location"
DAPP_REMARKS_NAME = "DApp Remarks"

STATUS_PENDING = "pending"
STATUS_PULLED = "pulled"
STATUS_IGNORED = "ignored because already pulled"

RECENT_HEADERS = [
    "Logged At",
    "Latitude",
    "Longitude",
    "Digital Signature",
    "Location ID",
    "Status",
]

MILES_DEDUPE = 20.0
HOURS_WINDOW = 24


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, atan2, cos, radians, sin, sqrt

    r = 3959.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def load_dotenv_repo() -> None:
    dl.load_dotenv_repo()


def parse_sheet_datetime(cell: str) -> datetime | None:
    s = (cell or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        # Google Sheets serial (days since 1899-12-30) as string/float
        serial = float(s)
        epoch = datetime(1899, 12, 30, tzinfo=timezone.utc)
        return epoch + timedelta(days=serial)
    except (TypeError, ValueError):
        return None


def _first_row_blank(rows: list[list[str]]) -> bool:
    if not rows:
        return True
    r0 = rows[0]
    if not r0:
        return True
    return all(str(c or "").strip() == "" for c in r0)


def ensure_recent_sheet(ws: gspread.Worksheet) -> dict[str, int]:
    rows = gspread_retry(ws.get_all_values)
    # Tab exists but no header row yet (empty grid or row 1 all blank) — same as GAS behavior.
    if not rows or _first_row_blank(rows):
        a1 = f"A1:{rowcol_to_a1(1, len(RECENT_HEADERS))}"
        gspread_retry(
            lambda: ws.update(a1, [RECENT_HEADERS], value_input_option="USER_ENTERED")
        )
        return {h: i for i, h in enumerate(RECENT_HEADERS)}
    hdr = [str(x or "").strip() for x in rows[0]]
    if hdr[: len(RECENT_HEADERS)] != RECENT_HEADERS:
        # Same as GAS: wrong placeholders in row 1 but no data rows yet — overwrite header row.
        if len(rows) <= 1:
            a1 = f"A1:{rowcol_to_a1(1, len(RECENT_HEADERS))}"
            gspread_retry(
                lambda: ws.update(a1, [RECENT_HEADERS], value_input_option="USER_ENTERED")
            )
            return {h: i for i, h in enumerate(RECENT_HEADERS)}
        raise SystemExit(
            f'"{RECENT_SHEET_NAME}" row 1 must be exactly: {", ".join(RECENT_HEADERS)} '
            f"(found {hdr[:6]!r}). Fix row 1 or clear conflicting rows below it.)"
        )
    return {h: i for i, h in enumerate(hdr)}


def ensure_dapp_remarks_headers(ws: gspread.Worksheet) -> list[str]:
    row = gspread_retry(lambda: ws.row_values(1))
    if not row:
        raise SystemExit(f'"{DAPP_REMARKS_NAME}" is missing a header row.')
    return row


def append_automation_remark(
    remark_ws: gspread.Worksheet,
    headers: list[str],
    *,
    remarks: str,
    submitted_by: str,
    shop_name: str = "(automation) Field agent Places pull",
    status: str = "Automation",
) -> None:
    hidx = {h: i for i, h in enumerate(headers)}
    row = [""] * len(headers)
    now_iso = datetime.now(timezone.utc).isoformat()

    def put(name: str, val: str) -> None:
        i = hidx.get(name)
        if i is not None:
            row[i] = val

    put("Submission ID", str(uuid.uuid4()))
    put("Shop Name", shop_name)
    put("Status", status)
    put("Remarks", remarks)
    put("Submitted By", submitted_by)
    put("Submitted At", now_iso)
    put("Processed", "Yes")
    put("Processed At", now_iso)
    gspread_retry(
        lambda: remark_ws.append_row(row, value_input_option="USER_ENTERED")
    )


def recent_pulled_within_window(
    all_rows: list[list[str]],
    col_idx: dict[str, int],
    *,
    now: datetime,
    lat0: float,
    lon0: float,
    miles_dedupe: float,
    hours_window: float,
) -> tuple[bool, str]:
    """True if any *pulled* row is within ``miles_dedupe`` and Logged At within ``hours_window`` of now."""
    i_logged = col_idx["Logged At"]
    i_lat = col_idx["Latitude"]
    i_lng = col_idx["Longitude"]
    i_stat = col_idx["Status"]
    cutoff = now - timedelta(hours=hours_window)
    for r in all_rows[1:]:
        if len(r) <= max(i_logged, i_lat, i_lng, i_stat):
            continue
        st = (r[i_stat] or "").strip()
        if st != STATUS_PULLED:
            continue
        ts = parse_sheet_datetime(r[i_logged] if i_logged < len(r) else "")
        if not ts:
            continue
        if ts < cutoff:
            continue
        try:
            la = float((r[i_lat] or "").strip())
            ln = float((r[i_lng] or "").strip())
        except ValueError:
            continue
        if haversine_miles(lat0, lon0, la, ln) <= miles_dedupe:
            return (
                True,
                f"Within {miles_dedupe:g} mi of a prior pull in the last {hours_window:g}h.",
            )
    return False, ""


def set_recent_status(
    ws: gspread.Worksheet,
    row_1based: int,
    col_status_1based: int,
    value: str,
) -> None:
    gspread_retry(
        lambda: ws.update_acell(
            rowcol_to_a1(row_1based, col_status_1based),
            value,
        )
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description="Recent Field Agent Location → Places Nearby → Hit List (deduped)."
    )
    p.add_argument("--limit", type=int, default=10, help="Max pending rows to process (default 10).")
    p.add_argument("--dry-run", action="store_true", help="Do not write sheets or call Places.")
    p.add_argument(
        "--keyword",
        default="health food organic wellness natural metaphysical apothecary",
        help="Places Nearby keyword (default holistic-oriented string).",
    )
    p.add_argument(
        "--radius-m",
        type=int,
        default=10000,
        help="Nearby Search radius in meters (default 10000).",
    )
    p.add_argument(
        "--dedupe-miles",
        type=float,
        default=MILES_DEDUPE,
        metavar="MI",
        help=(
            "Skip Places when another *pulled* Recent row is within this many miles and "
            f"within --dedupe-hours (default {MILES_DEDUPE:g}). "
            "Use --dedupe-miles 100 to approximate the old behavior; Hit List dedupe is unchanged."
        ),
    )
    p.add_argument(
        "--dedupe-hours",
        type=float,
        default=float(HOURS_WINDOW),
        metavar="H",
        help=(
            "Window for --dedupe-miles comparison against Logged At on *pulled* rows "
            f"(default {HOURS_WINDOW})."
        ),
    )
    p.add_argument(
        "--no-recent-dedupe",
        action="store_true",
        help="Never skip Places based on prior Recent *pulled* rows (Hit List dedupe still applies).",
    )
    args = p.parse_args()

    load_dotenv_repo()
    key = dl.maps_api_key() if not args.dry_run else ""
    client = dl.gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)

    try:
        recent_ws = sh.worksheet(RECENT_SHEET_NAME)
    except gspread.WorksheetNotFound:
        print(f'No sheet named "{RECENT_SHEET_NAME}" yet — nothing to do.', flush=True)
        return

    hit_ws = sh.worksheet(HIT_LIST_NAME)
    remark_ws = sh.worksheet(DAPP_REMARKS_NAME)

    col_idx = ensure_recent_sheet(recent_ws)
    remark_headers = ensure_dapp_remarks_headers(remark_ws)

    all_recent = gspread_retry(recent_ws.get_all_values)
    now = datetime.now(timezone.utc)

    pending_rows: list[tuple[int, list[str]]] = []
    i_stat = col_idx["Status"]
    for rn, row in enumerate(all_recent[1:], start=2):
        # Rows often omit trailing empty cells from the API; missing Status == not set yet.
        if not any(str(c or "").strip() for c in row):
            continue
        st = (row[i_stat] if len(row) > i_stat else "").strip().lower()
        if st in ("", STATUS_PENDING.lower()):
            pending_rows.append((rn, row))
        if len(pending_rows) >= args.limit:
            break

    if not pending_rows:
        print("No pending Recent Field Agent Location rows.", flush=True)
        return

    submitted_by = "field_agent_location_places_pull.py"

    for row_num, row in pending_rows:
        lat_s = row[col_idx["Latitude"]] if col_idx["Latitude"] < len(row) else ""
        lng_s = row[col_idx["Longitude"]] if col_idx["Longitude"] < len(row) else ""
        sig = row[col_idx["Digital Signature"]] if col_idx["Digital Signature"] < len(row) else ""
        loc_id = row[col_idx["Location ID"]] if col_idx["Location ID"] < len(row) else ""

        try:
            lat0 = float(str(lat_s).strip())
            lon0 = float(str(lng_s).strip())
        except ValueError:
            msg = f"Row {row_num}: invalid lat/lng ({lat_s!r}, {lng_s!r})."
            print(msg, flush=True)
            if not args.dry_run:
                set_recent_status(recent_ws, row_num, col_idx["Status"] + 1, STATUS_IGNORED)
                append_automation_remark(
                    remark_ws,
                    remark_headers,
                    remarks=msg,
                    submitted_by=submitted_by,
                )
            continue

        if args.no_recent_dedupe:
            dup, dup_reason = False, ""
        else:
            dup, dup_reason = recent_pulled_within_window(
                all_recent,
                col_idx,
                now=now,
                lat0=lat0,
                lon0=lon0,
                miles_dedupe=args.dedupe_miles,
                hours_window=args.dedupe_hours,
            )
        if dup:
            summary = (
                f"Location ID: {loc_id or '(none)'}\n"
                f"Agent lat/lng: {lat0}, {lon0}\n"
                f"Action: **{STATUS_IGNORED}** — {dup_reason}\n"
                f"Digital signature (truncated): {(sig or '')[:24]}…"
            )
            print(f"Row {row_num}: {STATUS_IGNORED}", flush=True)
            if not args.dry_run:
                set_recent_status(recent_ws, row_num, col_idx["Status"] + 1, STATUS_IGNORED)
                append_automation_remark(
                    remark_ws,
                    remark_headers,
                    remarks=summary,
                    submitted_by=submitted_by,
                )
                all_recent = gspread_retry(recent_ws.get_all_values)
            continue

        summary_lines = [
            f"Location ID: {loc_id or '(none)'}",
            f"Agent lat/lng: {lat0}, {lon0}",
            f"Digital signature (truncated): {(sig or '')[:24]}…",
        ]

        if args.dry_run:
            print(f"Row {row_num}: would call Places Nearby (dry-run).", flush=True)
            continue

        keys, place_ids, geo_name, name_addr = dl.extract_existing_for_dedupe(hit_ws)
        raw = dl.collect_nearby_for_center(
            key,
            lat0,
            lon0,
            min(args.radius_m, 50000),
            args.keyword,
            label=f"field_agent_row_{row_num}",
            sleep_s=2.0,
        )
        appended = 0
        skipped = 0
        appended_hit_rows: list[int] = []
        append_updated_ranges: list[str] = []
        for res in raw:
            pid = (res.get("place_id") or "").strip()
            if not pid:
                skipped += 1
                continue
            if pid in place_ids:
                skipped += 1
                continue
            name = (res.get("name") or "").strip()
            types = list(res.get("types") or [])
            vicinity = (res.get("vicinity") or "").strip()
            ex, _why = dl.should_exclude(name, types, vicinity)
            if ex:
                skipped += 1
                continue

            det = dl.place_details(key, pid)
            res_det = (det.get("result") or {}) if isinstance(det, dict) else {}
            if (res_det.get("business_status") or "").upper() in (
                "CLOSED_PERMANENTLY",
                "CLOSED_TEMPORARILY",
            ):
                skipped += 1
                continue

            comps = res_det.get("address_components") or []
            parsed = dl.parse_address_components(comps)
            street = parsed.get("street_line") or vicinity or ""
            city = parsed.get("city") or ""
            state = parsed.get("state") or ""
            lat = res_det.get("geometry", {}).get("location", {}).get("lat")
            lng = res_det.get("geometry", {}).get("location", {}).get("lng")
            if lat is None or lng is None:
                lat, lng = lat0, lon0

            phone = (res_det.get("formatted_phone_number") or "").strip()
            website = (res_det.get("website") or "").strip()
            shop_type = "Natural Goods"
            region_label = "field agent visit (DApp ping)"
            row_dict = dl.row_dict_for_append(
                name=name or "Unknown",
                street=street,
                city=city,
                state=state,
                lat=float(lat),
                lng=float(lng),
                phone=phone,
                website=website,
                shop_type=shop_type,
                place_id=pid,
                region_notes_label=region_label,
            )
            sk = row_dict.get("Store Key", "")
            if sk and sk in keys:
                skipped += 1
                continue
            fp = dl.geo_name_fingerprint(name, float(lat), float(lng))
            if fp and fp in geo_name:
                skipped += 1
                continue
            na = dl.name_address_fingerprint(name, street)
            if na and na in name_addr:
                skipped += 1
                continue

            out_row = [row_dict.get(c, "") for c in dl.HIT_LIST_COLS]
            append_res = gspread_retry(
                lambda r=out_row: hit_ws.append_row(r, value_input_option="USER_ENTERED")
            )
            ar_dict: dict[str, Any] = dict(append_res) if isinstance(append_res, Mapping) else {}
            upd = ar_dict.get("updates") if isinstance(ar_dict.get("updates"), Mapping) else {}
            ur = upd.get("updatedRange") or ar_dict.get("updatedRange")
            if ur:
                append_updated_ranges.append(str(ur))
            hit_lr = _parse_row_from_append_response(ar_dict)
            if hit_lr is None:
                nv = gspread_retry(hit_ws.get_all_values)
                hit_lr = len(nv) if nv else None
            if hit_lr is not None:
                appended_hit_rows.append(hit_lr)
            appended += 1
            keys.add(sk)
            place_ids.add(pid)
            if fp:
                geo_name.add(fp)
            if na:
                name_addr.add(na)
            time.sleep(0.06)

        if appended_hit_rows:
            try:
                n_au_av = write_au_av_for_hit_list_rows(hit_ws, appended_hit_rows)
                summary_lines.append(
                    f"Hit List AU/AV formulas applied to **{n_au_av}** new row(s) (warm-up / follow-up send counts)."
                )
            except Exception as exc:
                warn = f"AU/AV formula write failed ({exc}) — run `python3 scripts/set_hit_list_warmup_touches_formula.py` once."
                summary_lines.append(warn)
                print(f"Row {row_num}: warning: {warn}", flush=True)

        set_recent_status(recent_ws, row_num, col_idx["Status"] + 1, STATUS_PULLED)
        summary_lines.append(f"Places raw results: {len(raw)}")
        hit_append_line = f"Hit List rows appended: {appended}"
        if appended_hit_rows:
            hit_append_line += f" (sheet rows {', '.join(str(r) for r in appended_hit_rows)})"
        elif appended:
            hit_append_line += " (sheet row numbers unavailable from append response)"
        summary_lines.append(hit_append_line)
        if append_updated_ranges:
            summary_lines.append(
                "Google values.append updatedRange: " + "; ".join(append_updated_ranges)
            )
        summary_lines.append(f"Skipped (dedupe / filters): {skipped}")
        summary_lines.append(f"Status set on Recent tab: **{STATUS_PULLED}**")
        append_automation_remark(
            remark_ws,
            remark_headers,
            remarks="\n".join(summary_lines),
            submitted_by=submitted_by,
        )
        log_msg = f"Row {row_num}: pulled Places, appended {appended}, skipped {skipped}"
        if appended_hit_rows:
            log_msg += f"; Hit List sheet rows {', '.join(str(r) for r in appended_hit_rows)}"
        elif appended:
            log_msg += "; Hit List sheet rows (unavailable from append response)"
        print(log_msg + ".", flush=True)
        all_recent = gspread_retry(recent_ws.get_all_values)


if __name__ == "__main__":
    main()
