#!/usr/bin/env python3
"""
Append one row to the tab "OpenClaw Beer Hall updates" on the Telegram compilation sheet.

Usage:
  cd market_research && python3 scripts/append_openclaw_beer_hall_log.py \\
    --channel "Beer Hall" \\
    --tldr "$(printf '%s\n%s' 'Line one' 'Line two')" \\
    --links 'https://...' \\
    --pr-commit-links 'https://github.com/...' \\
    --openclaw-message-id '3EB0...' \\
    --notes 'optional'

Requires google_credentials.json and sheet shared with the service account (Editor).
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
SPREADSHEET_ID = "1qbZZhf-_7xzmDTriaJVWj6OZshyQsFkdsAV8-pyzASQ"
LOG_WS = "OpenClaw Beer Hall updates"
SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_client():
    if not _SA_CREDS.is_file():
        sys.stderr.write(f"Missing {_SA_CREDS}\n")
        sys.exit(1)
    creds = SACredentials.from_service_account_file(str(_SA_CREDS), scopes=SHEETS_SCOPES)
    return gspread.authorize(creds)


def main() -> None:
    p = argparse.ArgumentParser(description="Append a row to OpenClaw Beer Hall updates log tab.")
    p.add_argument("--channel", required=True, help='e.g. "Beer Hall" or "Founder Haus AI"')
    p.add_argument("--tldr", required=True, help="Plain-language TLDR (newlines allowed)")
    p.add_argument("--links", default="", help="Space- or newline-separated artifact URLs")
    p.add_argument("--pr-commit-links", default="", dest="pr_commit_links")
    p.add_argument("--openclaw-message-id", default="", dest="openclaw_message_id")
    p.add_argument("--notes", default="")
    p.add_argument(
        "--posted-at-utc",
        default="",
        dest="posted_at_utc",
        help="ISO UTC timestamp; default now",
    )
    args = p.parse_args()
    posted = args.posted_at_utc.strip() or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    gc = get_client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(LOG_WS)
    except gspread.WorksheetNotFound:
        sys.stderr.write(
            f"Tab {LOG_WS!r} not found. Run scripts/ensure_beer_hall_log_sheet.py first.\n"
        )
        sys.exit(1)

    row = [
        posted,
        args.channel.strip(),
        args.tldr.strip(),
        args.links.strip(),
        args.pr_commit_links.strip(),
        args.openclaw_message_id.strip(),
        args.notes.strip(),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    print(f"Appended row to {LOG_WS!r} (row {ws.row_count} approx).")


if __name__ == "__main__":
    main()
