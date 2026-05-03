#!/usr/bin/env python3
"""
Create the Hit List tab "Email Agent Drafts" with a standard header row if missing.

Use this registry alongside Gmail API drafts.create: each suggestion row tracks store context,
gmail_draft_id, and status. Optional Gmail user label: "Email Agent suggestions" (see HIT_LIST_CREDENTIALS.md).

Requires: google_credentials.json + spreadsheet shared with service account.

Usage:
  cd market_research && python3 scripts/ensure_email_agent_suggestions_sheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"
SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
SUGGESTIONS_WS = "Email Agent Drafts"
LEGACY_SUGGESTIONS_WS = "Email Agent Suggestions"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SUGGESTIONS_HEADERS = [
    "suggestion_id",
    "created_at_utc",
    "store_key",
    "shop_name",
    "to_email",
    "hit_list_row",
    "gmail_draft_id",
    "subject",
    "body_preview",
    "status",
    "gmail_label",
    "protocol_version",
    "notes",
    "Open",
    "Click through",
    "gmail_message_id",
]

# Before gmail_message_id (the 15-column generation that added Open / Click through).
SUGGESTIONS_HEADERS_PRE_MSG_ID = SUGGESTIONS_HEADERS[:-1]
# Before engagement columns (the 13-column original).
SUGGESTIONS_HEADERS_LEGACY = SUGGESTIONS_HEADERS_PRE_MSG_ID[:-2]

# Canonical label name to apply via Gmail API when creating drafts (future script).
DEFAULT_GMAIL_LABEL = "Email Agent suggestions"


def header_map(header_row: list[str]) -> dict[str, int]:
    return {str(c or "").strip(): i for i, c in enumerate(header_row) if str(c or "").strip()}


def migrate_drafts_add_open_click(ws: gspread.Worksheet, header_row: list[str]) -> bool:
    """Append **Open** and **Click through** at end of row 1 if missing; fill ``0`` for existing rows."""
    hm = header_map(header_row)
    if hm.get("Open") is not None and hm.get("Click through") is not None:
        return False

    # Append at the end of the row (sheet grid may be exactly full — use appendDimension).
    col_count_before = len(header_row)
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "appendDimension": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "length": 2,
                    }
                }
            ]
        }
    )
    c_open = col_count_before + 1
    c_click = col_count_before + 2
    ws.update_cell(1, c_open, "Open")
    ws.update_cell(1, c_click, "Click through")

    vals = ws.get_all_values()
    nrows = max(0, len(vals) - 1)
    if nrows:
        zeros = [["0", "0"]] * nrows
        ws.update(
            range_name=f"{rowcol_to_a1(2, c_open)}:{rowcol_to_a1(1 + nrows, c_click)}",
            values=zeros,
            value_input_option="USER_ENTERED",
        )

    print(
        "Migrated Email Agent Drafts: appended columns 'Open' and 'Click through' "
        f"(1-based columns {c_open}–{c_click}); filled 0 for {nrows} data row(s)."
    )
    return True


def migrate_drafts_add_message_id(ws: gspread.Worksheet, header_row: list[str]) -> bool:
    """Append **gmail_message_id** at end of row 1 if missing.

    Existing rows are left blank — `backfill_email_agent_drafts_message_id.py`
    walks pending_review rows and fills them by hitting Gmail draft API.
    """
    hm = header_map(header_row)
    if hm.get("gmail_message_id") is not None:
        return False

    col_count_before = len(header_row)
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "appendDimension": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "length": 1,
                    }
                }
            ]
        }
    )
    c_msg = col_count_before + 1
    ws.update_cell(1, c_msg, "gmail_message_id")
    print(
        "Migrated Email Agent Drafts: appended column 'gmail_message_id' "
        f"(1-based column {c_msg}). Existing rows left blank — run "
        "scripts/backfill_email_agent_drafts_message_id.py to populate "
        "pending_review rows from Gmail."
    )
    return True


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing service account {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(SUGGESTIONS_WS)
    except gspread.WorksheetNotFound:
        try:
            legacy = sh.worksheet(LEGACY_SUGGESTIONS_WS)
            legacy.update_title(SUGGESTIONS_WS)
            print(f"Renamed worksheet {LEGACY_SUGGESTIONS_WS!r} -> {SUGGESTIONS_WS!r}.")
            ws = sh.worksheet(SUGGESTIONS_WS)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=SUGGESTIONS_WS, rows=2000, cols=len(SUGGESTIONS_HEADERS))
            ws.append_row(SUGGESTIONS_HEADERS, value_input_option="USER_ENTERED")
            print(f"Created {SUGGESTIONS_WS!r} with header row ({len(SUGGESTIONS_HEADERS)} columns).")
            print(f"Optional Gmail label for drafts: {DEFAULT_GMAIL_LABEL!r}")
            return

    vals = ws.get_all_values()
    if not vals:
        ws.append_row(SUGGESTIONS_HEADERS, value_input_option="USER_ENTERED")
        print(f"{SUGGESTIONS_WS!r} was empty; wrote header row.")
        return

    first = [c.strip() for c in vals[0]]
    if first == SUGGESTIONS_HEADERS:
        print(f"{SUGGESTIONS_WS!r} already has the expected header row.")
        return

    if first == SUGGESTIONS_HEADERS_PRE_MSG_ID:
        migrate_drafts_add_message_id(ws, vals[0])
        print(f"{SUGGESTIONS_WS!r} migrated to include gmail_message_id.")
        return

    if first == SUGGESTIONS_HEADERS_LEGACY:
        migrate_drafts_add_open_click(ws, vals[0])
        # Re-read header after first migration, then chain the next.
        vals = ws.get_all_values()
        migrate_drafts_add_message_id(ws, [c.strip() for c in vals[0]])
        print(f"{SUGGESTIONS_WS!r} migrated to current schema (Open/Click + gmail_message_id).")
        return

    sys.stderr.write(
        f"{SUGGESTIONS_WS!r} row 1 does not match expected headers.\n"
        f"Expected (new): {SUGGESTIONS_HEADERS}\n"
        f"Or pre-msg-id (15 cols): {SUGGESTIONS_HEADERS_PRE_MSG_ID}\n"
        f"Or legacy (13 cols): {SUGGESTIONS_HEADERS_LEGACY}\n"
        f"Found:    {first}\n"
        "Fix manually or rename the tab if this is a different sheet.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
