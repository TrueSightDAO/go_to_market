#!/usr/bin/env python3
"""
Rewrite the spreadsheet tab "States" with canonical allowed values for the Hit List
and the Stores Nearby dapp (https://dapp.truesight.me/stores_nearby.html).

Use this so automation and manual edits use the same strings as `option value=` and
URL query params (`status=`, `shop_type=`).

Requires: market_research/google_credentials.json + sheet shared with service account.
See HIT_LIST_CREDENTIALS.md.

Usage:
  cd market_research && python3 scripts/populate_states_reference_sheet.py
  python3 scripts/populate_states_reference_sheet.py --dry-run   # print rows only
  python3 scripts/format_states_reference_sheet.py                 # layout / filters / banding
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
WS_TITLE = "States"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Mirrors dapp/stores_nearby.html <select id="newStoreStatus"> and status filter values.
STATUSES: list[tuple[str, str]] = [
    ("Research", "Store is being researched."),
    (
        "AI: Shortlisted",
        "Automated storefront photo rubric passed; operator can confirm human Shortlisted or override.",
    ),
    (
        "AI: Photo rejected",
        "Automated photo rubric failed (poor fit from imagery); operator can confirm Rejected/Not Appropriate or override.",
    ),
    (
        "AI: Photo needs review",
        "Rubric inconclusive; operator should review photos and set the next status.",
    ),
    ("Shortlisted", "Queued for outreach or visit."),
    ("Instagram Followed", "Followed on Instagram."),
    ("Contacted", "Initial contact made."),
    (
        "Manager Follow-up",
        "Visit done; follow up with manager using contact details.",
    ),
    (
        "Bulk Info Requested",
        "Buyer asked for wholesale or bulk pricing; use bulk-info email draft flow.",
    ),
    ("Meeting Scheduled", "Meeting or call scheduled."),
    ("Followed Up", "Follow-up with manager completed; awaiting next step."),
    ("Partnered", "Active partner."),
    ("On Hold", "Temporarily paused."),
    ("Rejected", "Declined or not interested."),
    ("Not Appropriate", "Poor fit for partnership."),
]

# Mirrors <select id="newStoreShopType"> — stored value uses slash, not " / ".
SHOP_TYPES: list[tuple[str, str]] = [
    (
        "Metaphysical/Spiritual",
        'UI label "Metaphysical / Spiritual". URL: shop_type=Metaphysical%2FSpiritual',
    ),
    ("Wellness Center", ""),
    ("Health Food Store", ""),
    ("Natural Goods", ""),
    ("Conscious Cafe", ""),
    ("Boutique Chocolate", ""),
    ("Antique Store", ""),
    ("Gift Shop", ""),
    ("Candy Store", ""),
    ("Yoga Studio", ""),
    ("Apothecary", ""),
    ("Other", ""),
]

# Mirrors <select id="newStoreState"> — two-letter codes only in Hit List col F.
US_STATES: list[tuple[str, str]] = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]

# Hit List column C — not exposed on stores_nearby suggest form; keep aligned for bulk edits.
PRIORITIES: list[str] = ["High", "Medium", "Low", "Existing Partner"]


def row(field: str, exact: str, notes: str, col: str) -> list[str]:
    return [field, exact, notes, col]


def build_table() -> list[list[str]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[list[str]] = [
        [
            "REFERENCE",
            "Use exact strings below in Hit List and for dapp sync. "
            "Do not use alternate spellings (e.g. Metaphysical / Spiritual with spaces only).",
            "",
            "",
        ],
        ["", "Live dapp", "https://dapp.truesight.me/stores_nearby.html", ""],
        ["", "Source", "dapp/stores_nearby.html (option values + stateNameLookup)", ""],
        ["refreshed_utc", now, "", ""],
        [],
        row("field", "exact_value", "notes", "hit_list_column"),
        [],
        row("— Status —", "", "Repeatable URL param: &status=<exact_value>", "B (Status)"),
    ]
    for val, note in STATUSES:
        out.append(row("Status", val, note, "B"))
    out.append([])
    out.append(
        row(
            "— Shop Type —",
            "",
            "URL: &shop_type=<exact_value> (encode / as %2F for Metaphysical/Spiritual)",
            "G (Shop Type)",
        )
    )
    for val, note in SHOP_TYPES:
        out.append(row("Shop Type", val, note, "G"))
    out.append([])
    out.append(
        row(
            "— US State (two-letter) —",
            "",
            "Match dapp dropdown values only (incl. DC).",
            "F (State)",
        )
    )
    for code, name in US_STATES:
        out.append(row("State", code, name, "F"))
    out.append([])
    out.append(
        row(
            "— Priority —",
            "",
            "Hit List column only; not on stores_nearby suggest-a-store form.",
            "C (Priority)",
        )
    )
    for p in PRIORITIES:
        out.append(row("Priority", p, "", "C"))
    return out


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    parser = argparse.ArgumentParser(description='Populate "States" reference tab from dapp enums.')
    parser.add_argument("--dry-run", action="store_true", help="Print table; do not write Sheets.")
    args = parser.parse_args()

    table = build_table()
    if args.dry_run:
        for r in table:
            print("\t".join(r))
        print(f"\nRows: {len(table)}", file=sys.stderr)
        return

    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(WS_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WS_TITLE, rows=len(table) + 50, cols=6)

    ws.clear()
    # Expand if needed
    need_rows = max(ws.row_count, len(table) + 10)
    if ws.row_count < need_rows:
        ws.resize(rows=need_rows, cols=max(ws.col_count, 5))

    ws.update(
        values=table,
        range_name="A1",
        value_input_option="USER_ENTERED",
    )
    print(f"Wrote {len(table)} rows to tab {WS_TITLE!r} in spreadsheet {SPREADSHEET_ID}.")


if __name__ == "__main__":
    main()
