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
]

# Canonical label name to apply via Gmail API when creating drafts (future script).
DEFAULT_GMAIL_LABEL = "Email Agent suggestions"


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

    sys.stderr.write(
        f"{SUGGESTIONS_WS!r} row 1 does not match expected headers.\n"
        f"Expected: {SUGGESTIONS_HEADERS}\n"
        f"Found:    {first}\n"
        "Fix manually or rename the tab if this is a different sheet.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
