#!/usr/bin/env python3
"""
Backfill ``thread_id`` on **Email Agent Drafts** and **Email Agent Follow Up**.

Does batch lookups and writes to stay under Sheets API quotas.

Usage:
  cd market_research
  python3 scripts/backfill_thread_id.py --dry-run
  python3 scripts/backfill_thread_id.py --tab followup
  python3 scripts/backfill_thread_id.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_REPO = Path(__file__).resolve().parent.parent
_SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"


def _load_gmail_creds():
    token_json = os.environ.get("GMAIL_TOKEN_JSON") or ""
    if token_json:
        creds_data = json.loads(token_json)
        return Credentials.from_authorized_user_info(creds_data)
    token_path = _REPO / "credentials" / "gmail" / "token.json"
    if token_path.is_file():
        with open(token_path) as f:
            return Credentials.from_authorized_user_info(json.load(f))
    sys.exit("No Gmail credentials found.")


def _thread_id_from_draft(gsvc, draft_id: str) -> str:
    try:
        d = gsvc.users().drafts().get(userId="me", id=draft_id, format="minimal").execute()
        return (d.get("message") or {}).get("threadId", "") or ""
    except HttpError as e:
        if e.resp.status in (404, 400):
            return ""
        raise


def _thread_id_from_message(gsvc, msg_id: str) -> str:
    try:
        m = gsvc.users().messages().get(userId="me", id=msg_id, format="minimal").execute()
        return m.get("threadId", "") or ""
    except HttpError as e:
        if e.resp.status in (404, 400):
            return ""
        raise


def _backfill_tab(
    gsvc,
    sheet,
    tab_name: str,
    thread_col_letter: str,
    thread_col_zero: int,
    id_cols: list[tuple[int, str]],  # [(col_index, 'draft'|'message'), ...]
    dry_run: bool,
) -> int:
    ws = sheet.worksheet(tab_name)
    values = ws.get_all_values()
    if len(values) < 2:
        print(f"{tab_name}: no data rows")
        return 0

    hdr = {v.lower(): i for i, v in enumerate(values[0])}

    # Gather all rows that need backfill
    updates: list[tuple[int, str, str]] = []  # (row_num, id_value, 'draft'|'message')
    for r, row in enumerate(values[1:], start=2):
        existing = (row[thread_col_zero] if thread_col_zero < len(row) else "").strip()
        if existing:
            continue
        for col_i, id_type in id_cols:
            if col_i is not None and col_i < len(row):
                gid = row[col_i].strip()
                if gid:
                    updates.append((r, gid, id_type))
                    break

    if not updates:
        print(f"{tab_name}: all rows already have thread_id or no Gmail IDs")
        return 0

    print(f"{tab_name}: {len(updates)} rows to backfill")

    # Batch write in chunks to avoid rate limits
    chunk_size = 40
    n_filled = 0
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i : i + chunk_size]
        batch_data = []
        for row_num, gid, id_type in chunk:
            tid = ""
            if not dry_run:
                if id_type == "draft":
                    tid = _thread_id_from_draft(gsvc, gid)
                    if not tid:
                        tid = _thread_id_from_message(gsvc, gid)
                else:
                    tid = _thread_id_from_message(gsvc, gid)
            else:
                tid = f"<thread for {id_type} {gid[:12]}>"

            if tid:
                batch_data.append({"range": f"{tab_name}!{thread_col_letter}{row_num}", "values": [[tid]]})
                n_filled += 1

        if batch_data and not dry_run:
            # Use single batch update call
            from googleapiclient.discovery import build as build_sheets

            sa = sheet.client.auth
            sheets_api = build_sheets("sheets", "v4", credentials=sa)
            sheets_api.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet.id,
                body={"data": batch_data, "valueInputOption": "USER_ENTERED"},
            ).execute()
            print(f"  ... wrote chunk {i // chunk_size + 1}: {len(batch_data)} rows")

        if dry_run:
            for bd in batch_data[:3]:
                print(f"  dry-run: {bd['range']} = {bd['values']}")
            print(f"  ... {len(batch_data)} total would be written")

    print(f"{tab_name}: filled {n_filled} row(s) dry_run={dry_run}")
    return n_filled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tab", choices=["drafts", "followup", "both"], default="both")
    args = parser.parse_args()

    gc = gspread.service_account(filename=str(_REPO / "google_credentials.json"))
    sheet = gc.open_by_key(_SPREADSHEET_ID)

    gsvc = None
    if not args.dry_run:
        gcreds = _load_gmail_creds()
        gsvc = build("gmail", "v1", credentials=gcreds, cache_discovery=False)

    if args.tab in ("drafts", "both"):
        # Drafts: col P = gmail_message_id (index 15) is faster, col G = gmail_draft_id (index 6) as fallback
        _backfill_tab(
            gsvc,
            sheet,
            "Email Agent Drafts",
            thread_col_letter="Q",
            thread_col_zero=16,
            id_cols=[(15, "message"), (6, "draft")],
            dry_run=args.dry_run,
        )

    if args.tab in ("followup", "both"):
        # Follow Up: col A = gmail_message_id (index 0)
        _backfill_tab(
            gsvc,
            sheet,
            "Email Agent Follow Up",
            thread_col_letter="O",
            thread_col_zero=14,
            id_cols=[(0, "message")],
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
