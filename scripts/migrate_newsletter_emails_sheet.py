#!/usr/bin/env python3
"""
One-off migration: copy every row from the legacy **Agroverse News Letter Emails**
tab on the main ledger workbook into the same-named tab on a destination workbook.

Uses **market_research/google_credentials.json** (same service account as
`send_newsletter.py`): **agroverse-market-research@get-data-io.iam.gserviceaccount.com**.
That identity must have **read** access to the source file and **write** access
to the destination file.

Edgar open/click updates use a **different** service account
(`edgar-dapp-listener@…`); grant it **Editor** on the destination workbook before
pointing `Gdrive::NewsletterEmails` at the new ID.

Examples:
  cd market_research
  python3 scripts/migrate_newsletter_emails_sheet.py --dry-run
  python3 scripts/migrate_newsletter_emails_sheet.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

# Source: main ledger (legacy)
SOURCE_SPREADSHEET_ID = "1GE7PUq-UT6x2rBN-Q2ksogbWpgyuh2SaxJyG_uEK6PU"
# Destination: dedicated newsletter workbook (operator-created)
DEFAULT_TARGET_SPREADSHEET_ID = "1ed3q3SJ8ztGwfWit6Wxz_S72Cn5jKQFkNrHpeOVXP8s"

SHEET_NAME = "Agroverse News Letter Emails"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_sheets_client():
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def _col_letter(idx_1based: int) -> str:
    s = ""
    n = idx_1based
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def ensure_destination_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        return sh.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=SHEET_NAME, rows=2000, cols=20)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-id", default=SOURCE_SPREADSHEET_ID, help="Source spreadsheet ID")
    p.add_argument("--target-id", default=DEFAULT_TARGET_SPREADSHEET_ID, help="Destination spreadsheet ID")
    p.add_argument("--dry-run", action="store_true", help="Print counts only; do not write")
    p.add_argument("--yes", action="store_true", help="Required to perform the write")
    args = p.parse_args(argv)

    if not _SA_CREDS.is_file():
        print(f"Missing service account file: {_SA_CREDS}", file=sys.stderr)
        return 1

    gc = get_sheets_client()
    src_sh = gc.open_by_key(args.source_id)
    dst_sh = gc.open_by_key(args.target_id)
    src_ws = src_sh.worksheet(SHEET_NAME)
    rows = src_ws.get_all_values()
    if not rows:
        print("Source tab is empty; nothing to migrate.", file=sys.stderr)
        return 1

    nrows = len(rows)
    ncols = max(len(r) for r in rows) if rows else 0
    print(f"Source {args.source_id!r} tab {SHEET_NAME!r}: {nrows} row(s), up to {ncols} column(s).")

    if args.dry_run:
        print("Dry run: no changes made.")
        return 0

    if not args.yes:
        print("Refusing to write without --yes (use --dry-run first).", file=sys.stderr)
        return 1

    dst_ws = ensure_destination_worksheet(dst_sh)
    dst_ws.clear()
    last_col = _col_letter(max(len(r) for r in rows))
    rng = f"A1:{last_col}{len(rows)}"
    dst_ws.update(rng, rows, value_input_option="USER_ENTERED")
    dst_ws.format(f"A1:{last_col}1", {"textFormat": {"bold": True}})
    dst_sh.batch_update(
        {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": dst_ws.id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                }
            ]
        }
    )
    print(f"Migrated {nrows} row(s) into {args.target_id!r} → {SHEET_NAME!r} (range {rng}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
