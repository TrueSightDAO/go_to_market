#!/usr/bin/env python3
"""
Create the tab "OpenClaw Beer Hall updates" on the TrueSight DAO Telegram compilation
spreadsheet if missing, with a standard header row for logging OpenClaw → WhatsApp digests.

If the legacy tab "Beer_Hall_Posts" exists, it is renamed to "OpenClaw Beer Hall updates".

Prevents duplicate/missed items across sessions: append one row per post (Beer Hall and/or
Founder Haus AI). See agentic_ai_context OPENCLAW_WHATSAPP.md (outbound digests).

Requires: market_research/google_credentials.json (service account). Share the spreadsheet
with the service account client_email as Editor.

Spreadsheet: https://docs.google.com/spreadsheets/d/1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ/edit

Usage:
  cd market_research && python3 scripts/ensure_beer_hall_log_sheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials as SACredentials

_REPO = Path(__file__).resolve().parent.parent
_SA_CREDS = _REPO / "google_credentials.json"

# TrueSight DAO Telegram compilation
SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
LOG_WS = "OpenClaw Beer Hall updates"
LEGACY_WS = "Beer_Hall_Posts"

SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LOG_HEADERS = [
    "posted_at_utc",
    "channel",
    "tldr",
    "links",
    "pr_commit_links",
    "openclaw_message_id",
    "notes",
]


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(
            f"Missing service account JSON at {_SA_CREDS}\n"
            "Place google_credentials.json in market_research/ and share the sheet with its client_email.\n"
        )
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def open_log_worksheet(sh: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        return sh.worksheet(LOG_WS)
    except gspread.WorksheetNotFound:
        pass
    try:
        legacy = sh.worksheet(LEGACY_WS)
        legacy.update_title(LOG_WS)
        print(f"Renamed legacy tab {LEGACY_WS!r} → {LOG_WS!r}.")
        return sh.worksheet(LOG_WS)
    except gspread.WorksheetNotFound:
        pass
    ws = sh.add_worksheet(title=LOG_WS, rows=2000, cols=len(LOG_HEADERS))
    ws.append_row(LOG_HEADERS, value_input_option="USER_ENTERED")
    print(f"Created tab {LOG_WS!r} with header row ({len(LOG_HEADERS)} columns).")
    print(
        "Append one row per WhatsApp digest. channel: Beer Hall | Founder Haus AI\n"
        f"Sheet: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
    )
    return ws


def main() -> None:
    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = open_log_worksheet(sh)

    vals = ws.get_all_values()
    if not vals:
        ws.append_row(LOG_HEADERS, value_input_option="USER_ENTERED")
        print(f"{LOG_WS!r} was empty; wrote header row.")
        return

    first = [c.strip() for c in vals[0]]
    if first == LOG_HEADERS:
        print(f"{LOG_WS!r} already has the expected header row.")
        return

    sys.stderr.write(
        f"{LOG_WS!r} row 1 does not match expected headers.\n"
        f"Expected: {LOG_HEADERS}\n"
        f"Found:    {first}\n"
        "Fix manually or rename the tab if this is a different sheet.\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
