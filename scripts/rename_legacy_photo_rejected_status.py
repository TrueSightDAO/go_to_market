#!/usr/bin/env python3
"""
One-off migration: rename Hit List rows with Status == 'AI: Photo rejected'
to 'AI: No fit signal'.

The photo+Grok rubric was retired in PR #101 (2026-05-03). The status name
'AI: Photo rejected' is now misleading — it gets written by the
site-crawl-no-signal path in detect_circle_hosting_retailers.py, and has
nothing to do with photos. PR #102 (2026-05-03) renamed the canonical
write target to 'AI: No fit signal' and added the legacy name to the
rescue path's accepted-input set.

This script does the one-time data migration to bring existing rows in
line with the new name. Idempotent — already-renamed rows are skipped.

Audit trail: every renamed row gets a DApp Remarks entry explaining the
state-name migration with a stable reason code so it's distinguishable
from any future Status flips.

Usage:
    cd market_research
    python3 scripts/rename_legacy_photo_rejected_status.py --dry-run
    python3 scripts/rename_legacy_photo_rejected_status.py             # do it
    python3 scripts/rename_legacy_photo_rejected_status.py --limit 50  # batch
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from hit_list_dapp_remarks_sheet import append_dapp_remark_and_apply  # noqa: E402

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WS = "Hit List"
DAPP_REMARKS_WS = "DApp Remarks"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LEGACY_STATUS = "AI: Photo rejected"
NEW_STATUS = "AI: No fit signal"
SUBMITTED_BY = "rename_legacy_photo_rejected_status"


def gspread_client() -> gspread.Client:
    creds_path = REPO / "google_credentials.json"
    if not creds_path.is_file():
        raise SystemExit(f"Missing service account JSON: {creds_path}")
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=None,
                   help="Cap rows renamed this run (default: all matching).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would change without touching the sheet.")
    p.add_argument("--sleep", type=float, default=0.3,
                   help="Sleep between writes in seconds (default 0.3).")
    args = p.parse_args(argv)

    gc = gspread_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    hit_ws = sh.worksheet(HIT_LIST_WS)
    remark_ws = sh.worksheet(DAPP_REMARKS_WS)
    rows = hit_ws.get_all_values()
    if len(rows) < 2:
        print("No data rows.")
        return 0
    header = [str(x or "").strip() for x in rows[0]]
    if "Status" not in header or "Shop Name" not in header:
        print("Hit List missing required columns.")
        return 1
    i_status = header.index("Status")
    i_shop = header.index("Shop Name")

    # Find rows currently at the legacy status.
    targets: list[tuple[int, str]] = []
    for ri, raw in enumerate(rows[1:], start=2):
        row = list(raw) + [""] * (len(header) - len(raw))
        if (row[i_status] or "").strip() == LEGACY_STATUS:
            shop = (row[i_shop] or "").strip()
            targets.append((ri, shop))

    print(f"Hit List rows total: {len(rows) - 1}")
    print(f"Rows at legacy '{LEGACY_STATUS}': {len(targets)}")
    if args.limit is not None:
        targets = targets[: args.limit]
        print(f"Limiting to first {len(targets)} for this run.")

    if not targets:
        print("Nothing to migrate.")
        return 0

    renamed = 0
    failures = 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for ri, shop in targets:
        if args.dry_run:
            print(f"  [dry] row {ri} {shop!r}: {LEGACY_STATUS!r} -> {NEW_STATUS!r}")
            renamed += 1
            continue

        submission_id = str(uuid.uuid4())
        submitted_at = datetime.now(timezone.utc).strftime("%m/%d/%Y %H:%M:%S")
        remark = (
            f"[status-rename {stamp}] outcome=rename_legacy_photo_rejected "
            f"from={LEGACY_STATUS!r} to={NEW_STATUS!r} "
            f"(photo+Grok rubric retired 2026-05-03; site crawl is canonical "
            f"qualifier; new status name reflects evidence)"
        )
        try:
            append_dapp_remark_and_apply(
                hit_ws, remark_ws, ri, shop,
                NEW_STATUS, remark,
                SUBMITTED_BY, submitted_at, submission_id,
            )
            renamed += 1
            print(f"  [rename] row {ri} {shop!r}: -> {NEW_STATUS}")
        except Exception as e:
            failures += 1
            sys.stderr.write(f"  [fail] row {ri} {shop!r}: {e}\n")
        time.sleep(max(0.0, args.sleep))

    print()
    print(f"Renamed:   {renamed}")
    print(f"Failures:  {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
