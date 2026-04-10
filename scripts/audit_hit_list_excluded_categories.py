#!/usr/bin/env python3
"""
Scan Hit List rows, detect Google exclude categories (same rules as
discover_apothecaries_la_hit_list.should_exclude), set Status to **Not Appropriate**,
and append a **DApp Remarks** row with category + reason (Processed) so downstream
jobs can skip these rows.

Uses **place_id** from Notes when present (Place Details for types + vicinity); otherwise
name/vicinity-only heuristics (same as discovery).

**Scope:** only rows whose Status is **Research** or starts with **AI:** (other statuses are skipped).

Usage:
  cd market_research
  python3 scripts/audit_hit_list_excluded_categories.py --dry-run
  python3 scripts/audit_hit_list_excluded_categories.py --limit 50
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts"))

from discover_apothecaries_la_hit_list import (  # noqa: E402
    EXCLUDE_TYPES,
    SPREADSHEET_ID,
    HIT_LIST_WS,
    gspread_client,
    maps_api_key,
    place_details,
    should_exclude,
)
from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply, gspread_retry  # noqa: E402

DAPP_REMARKS_WS = "DApp Remarks"
SUBMITTED_BY = "hit_list_exclude_category_audit"

PLACE_ID_RE = re.compile(r"(?i)place[_\s-]*id\s*:\s*([A-Za-z0-9_-]{12,})")

# Do not re-audit terminal / already-flagged rows.
SKIP_STATUS = frozenset(
    {
        "Not Appropriate",
        "Rejected",
        "Partnered",
        "On Hold",
    }
)


def status_in_audit_scope(status: str) -> bool:
    """Only Research or AI-prefixed statuses (e.g. AI: Shortlisted, AI: Enrich with contact)."""
    s = (status or "").strip()
    return s == "Research" or s.startswith("AI:")


def extract_place_id(notes: str) -> str | None:
    m = PLACE_ID_RE.search(notes or "")
    return m.group(1).strip() if m else None


def category_and_reason_for_remark(
    why: str,
    types: list[str],
) -> tuple[str, str]:
    """Human-readable category line + reason line for DApp Remarks."""
    tset = {x.lower() for x in (types or [])}
    matched_types = sorted(EXCLUDE_TYPES & tset)

    if why == "google_type_excluded" or matched_types:
        cat = "Google Places types: " + (
            ", ".join(matched_types) if matched_types else "excluded (see Place Details)"
        )
        reason = (
            "Listing is categorized under excluded Place types (pharmacy, mall, bar/drink venue, etc.); "
            "not a target for metaphysical retail outreach."
        )
        return cat, reason

    if why.startswith("bar_name:"):
        frag = why.split(":", 1)[1].strip()
        cat = f"Drink / bar venue (name or vicinity match: {frag})"
        reason = "Themed cocktail or bar naming; not metaphysical retail."
        return cat, reason

    if why.startswith("pharmacy_name:"):
        frag = why.split(":", 1)[1].strip()
        cat = f"Pharmacy / chain (name match: {frag})"
        reason = "Chain pharmacy or prescription retail; not target channel."
        return cat, reason

    if why.startswith("cannabis:"):
        frag = why.split(":", 1)[1].strip()
        cat = f"Cannabis retail (name match: {frag})"
        reason = "Excluded category for this pipeline."
        return cat, reason

    if why.startswith("chain:"):
        frag = why.split(":", 1)[1].strip()
        cat = f"Chain vitamin / mass retail (name match: {frag})"
        reason = "Excluded category for this pipeline."
        return cat, reason

    if why.startswith("cosmetics:"):
        frag = why.split(":", 1)[1].strip()
        cat = f"Cosmetics / department retail (name match: {frag})"
        reason = "High-street beauty retail; not metaphysical indie target."
        return cat, reason

    cat = f"Excluded heuristic (code: {why})"
    reason = "Matched automated exclude rules; not appropriate for this list."
    return cat, reason


def build_remarks_body(cat: str, reason: str) -> str:
    return (
        "Automated audit (exclude categories). "
        f"Category: {cat}. "
        f"Reason: {reason} "
        "Marking Not Appropriate so photo research / enrichment does not spend on this row."
    )


def col_index(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise SystemExit(f'Hit List missing column "{name}".')


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mark Hit List rows Not Appropriate when exclude rules match; append DApp Remarks."
    )
    p.add_argument("--dry-run", action="store_true", help="Print matches only; no sheet writes.")
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max rows to update this run (0 = no cap).",
    )
    p.add_argument(
        "--sleep-details",
        type=float,
        default=0.1,
        help="Seconds after each Place Details call (default 0.1).",
    )
    args = p.parse_args()

    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)

    rows = gspread_retry(lambda: hit_ws.get_all_values())
    if len(rows) < 2:
        print("No data rows.")
        return

    header = rows[0]
    i_name = col_index(header, "Shop Name")
    i_status = col_index(header, "Status")
    i_notes = col_index(header, "Notes")

    remark_headers: list[str] | None = None
    remark_ws = None
    if not args.dry_run:
        remark_ws = sh.worksheet(DAPP_REMARKS_WS)
        remark_headers = gspread_retry(lambda: remark_ws.row_values(1))

    key = None
    submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")

    updated = 0
    skipped_terminal = 0
    skipped_ineligible_scope = 0
    skipped_ok = 0
    details_errors = 0

    for ri, row in enumerate(rows[1:], start=2):
        if args.limit and updated >= args.limit:
            break

        def cell(i: int) -> str:
            return row[i].strip() if i < len(row) else ""

        name = cell(i_name)
        status = cell(i_status)
        notes = cell(i_notes)

        if not name:
            continue
        if status in SKIP_STATUS:
            skipped_terminal += 1
            continue
        if not status_in_audit_scope(status):
            skipped_ineligible_scope += 1
            continue

        types: list[str] = []
        vicinity = ""
        use_name = name

        pid = extract_place_id(notes)
        if pid:
            if key is None:
                key = maps_api_key()
            try:
                det = place_details(key, pid)
                time.sleep(max(0.0, args.sleep_details))
                if det.get("status") == "OK":
                    res = det.get("result") or {}
                    use_name = (res.get("name") or name).strip() or name
                    types = list(res.get("types") or [])
                    vicinity = (res.get("vicinity") or res.get("formatted_address") or "").strip()
                else:
                    details_errors += 1
            except Exception as exc:
                print(f"  row {ri} place_details error: {exc}", flush=True)
                details_errors += 1

        bad, why = should_exclude(use_name, types, vicinity)
        if not bad:
            skipped_ok += 1
            continue

        cat, reason = category_and_reason_for_remark(why, types)
        remarks = build_remarks_body(cat, reason)

        print(
            f"  MATCH row {ri} {name!r} | was {status!r} | why={why!r} | types={types[:6]!r}...",
            flush=True,
        )

        if args.dry_run:
            updated += 1
            continue

        assert remark_ws is not None
        append_dapp_remark_and_apply(
            hit_ws,
            remark_ws,
            ri,
            use_name,
            "Not Appropriate",
            remarks,
            SUBMITTED_BY,
            submitted_at,
            str(uuid.uuid4()),
            hit_headers=header,
            remark_headers=remark_headers,
        )
        updated += 1
        time.sleep(1.0)

    print("\n--- Summary ---", flush=True)
    print(f"  rows_marked_not_appropriate: {updated}", flush=True)
    print(f"  skipped_terminal_status: {skipped_terminal}", flush=True)
    print(f"  skipped_not_research_or_ai: {skipped_ineligible_scope}", flush=True)
    print(f"  rows_no_match: {skipped_ok}", flush=True)
    print(f"  place_details_errors: {details_errors}", flush=True)
    if args.dry_run:
        print("  (dry-run: no writes)", flush=True)


if __name__ == "__main__":
    main()
