#!/usr/bin/env python3
"""
Process unhandled DApp remarks and apply them to the Hit List sheet.

For each unprocessed entry in the "DApp Remarks" worksheet:
  * Update the matching shop's status (if provided)
  * Append the remark to the "Sales Process Notes" field with a timestamp
  * Mark the remark row as processed with the current timestamp

Usage:
    python3 process_dapp_remarks.py                # process all pending entries
    python3 process_dapp_remarks.py --dry-run      # show actions without modifying the sheet
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"
DAPP_REMARKS_SHEET = "DApp Remarks"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    # Look for credentials in parent directory (repository root)
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {creds_path}. "
            "Please add google_credentials.json with service account credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    return client


def build_header_index(headers: List[str]) -> Dict[str, int]:
    """Return a mapping from header name to column index (0-based)."""
    return {header: idx for idx, header in enumerate(headers)}


def append_sales_note(existing_notes: str, note_line: str) -> str:
    if not existing_notes:
        return note_line
    return f"{existing_notes.strip()}\n\n{note_line}"


def process_remarks(dry_run: bool = False) -> Tuple[int, int]:
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        hit_list_ws = spreadsheet.worksheet(HIT_LIST_SHEET)
    except gspread.WorksheetNotFound:
        raise ValueError(f'Worksheet "{HIT_LIST_SHEET}" not found.')

    try:
        remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
    except gspread.WorksheetNotFound:
        raise ValueError(
            f'Worksheet "{DAPP_REMARKS_SHEET}" not found. '
            "Run generate_shop_list.py first to initialise it."
        )

    hit_values = hit_list_ws.get_all_values()
    if len(hit_values) < 2:
        raise ValueError("Hit List worksheet is empty; nothing to update.")

    remarks_values = remarks_ws.get_all_values()
    if len(remarks_values) < 2:
        print("No remarks to process.")
        return 0, 0

    hit_headers = hit_values[0]
    hit_index = build_header_index(hit_headers)
    required_columns = ["Shop Name", "Status", "Sales Process Notes", "Status Updated By", "Status Updated Date"]
    for col in required_columns:
        if col not in hit_index:
            raise ValueError(f'Missing column "{col}" in Hit List worksheet.')

    remarks_headers = remarks_values[0]
    remarks_index = build_header_index(remarks_headers)
    for col in ["Submission ID", "Shop Name", "Status", "Remarks", "Submitted By", "Processed", "Processed At"]:
        if col not in remarks_index:
            raise ValueError(f'Missing column "{col}" in DApp Remarks worksheet.')

    # Build lookup for shop rows (exact match on Shop Name)
    shop_row_lookup: Dict[str, int] = {}
    for row_num, row in enumerate(hit_values[1:], start=2):  # 1-indexed rows
        name = row[hit_index["Shop Name"]].strip()
        if name:
            shop_row_lookup[name.lower()] = row_num

    processed_count = 0
    skipped_count = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    for row_num, row in enumerate(remarks_values[1:], start=2):
        processed_flag = row[remarks_index["Processed"]].strip()
        if processed_flag.lower() == "yes":
            continue  # already processed

        shop_name = row[remarks_index["Shop Name"]].strip()
        status = row[remarks_index["Status"]].strip()
        remarks = row[remarks_index["Remarks"]].strip()
        submitted_by = row[remarks_index["Submitted By"]].strip() or "DApp"
        submitted_at = row[remarks_index.get("Submitted At", -1)].strip() if "Submitted At" in remarks_index else ""

        if not shop_name:
            print(f"[SKIP] Row {row_num}: Missing shop name.")
            skipped_count += 1
            continue

        lookup_key = shop_name.lower()
        target_row = shop_row_lookup.get(lookup_key)
        if not target_row:
            print(f"[SKIP] Row {row_num}: Shop '{shop_name}' not found in Hit List.")
            skipped_count += 1
            continue

        print(f"[INFO] Updating '{shop_name}' (Hit List row {target_row}) with status '{status}' and remarks.")

        if not dry_run:
            if status:
                hit_list_ws.update_cell(target_row, hit_index["Status"] + 1, status)

            status_note = remarks or ""
            if status_note:
                note_prefix = f"[{now_iso} | {submitted_by}]"
                if submitted_at:
                    note_prefix = f"[{submitted_at} | {submitted_by}]"
                note_line = f"{note_prefix} {status_note}"
                existing_notes = hit_list_ws.cell(target_row, hit_index["Sales Process Notes"] + 1).value or ""
                new_notes = append_sales_note(existing_notes, note_line)
                hit_list_ws.update_cell(target_row, hit_index["Sales Process Notes"] + 1, new_notes)

            if "Status Updated By" in hit_index:
                hit_list_ws.update_cell(target_row, hit_index["Status Updated By"] + 1, submitted_by)
            if "Status Updated Date" in hit_index:
                hit_list_ws.update_cell(target_row, hit_index["Status Updated Date"] + 1, now_iso)

            remarks_ws.update_cell(row_num, remarks_index["Processed"] + 1, "Yes")
            remarks_ws.update_cell(row_num, remarks_index["Processed At"] + 1, now_iso)

        processed_count += 1

    if processed_count == 0:
        print("No new remarks to process.")
    else:
        print(f"Processed {processed_count} remark(s). Skipped {skipped_count}.")

    return processed_count, skipped_count


def main():
    parser = argparse.ArgumentParser(description="Process DApp remarks into Hit List.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without updating the sheet.")
    args = parser.parse_args()

    process_remarks(dry_run=args.dry_run)


if __name__ == "__main__":
    main()

