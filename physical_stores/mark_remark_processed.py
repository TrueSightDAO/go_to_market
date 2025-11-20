#!/usr/bin/env python3
"""Mark a specific remark as processed in the DApp Remarks sheet."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
DAPP_REMARKS_SHEET = "DApp Remarks"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
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


def mark_remark_processed(submission_id: str) -> None:
    """Mark a remark as processed."""
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    remarks_ws = spreadsheet.worksheet(DAPP_REMARKS_SHEET)
    
    all_values = remarks_ws.get_all_values()
    if len(all_values) < 2:
        print("No remarks found.")
        return
    
    headers = all_values[0]
    headers_idx = {header: idx for idx, header in enumerate(headers)}
    
    if "Submission ID" not in headers_idx:
        raise ValueError("'Submission ID' column not found")
    if "Processed" not in headers_idx:
        raise ValueError("'Processed' column not found")
    if "Processed At" not in headers_idx:
        raise ValueError("'Processed At' column not found")
    
    submission_id_idx = headers_idx["Submission ID"]
    processed_idx = headers_idx["Processed"]
    processed_at_idx = headers_idx["Processed At"]
    
    # Find the remark
    for row_num, row in enumerate(all_values[1:], start=2):
        if submission_id_idx < len(row) and row[submission_id_idx].strip() == submission_id:
            # Check current status
            current_processed = row[processed_idx].strip() if processed_idx < len(row) else ""
            
            if current_processed.lower() == "yes":
                print(f"✅ Remark {submission_id} is already marked as processed.")
                return
            
            # Mark as processed
            now_iso = datetime.now(timezone.utc).isoformat()
            remarks_ws.update_cell(row_num, processed_idx + 1, "Yes")
            remarks_ws.update_cell(row_num, processed_at_idx + 1, now_iso)
            
            shop_name = row[headers_idx.get("Shop Name", -1)] if "Shop Name" in headers_idx and headers_idx["Shop Name"] < len(row) else "Unknown"
            print(f"✅ Marked remark {submission_id} as processed")
            print(f"   Shop: {shop_name}")
            print(f"   Processed At: {now_iso}")
            return
    
    raise ValueError(f"Remark with Submission ID '{submission_id}' not found")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 mark_remark_processed.py <submission_id>")
        sys.exit(1)
    
    submission_id = sys.argv[1]
    
    try:
        mark_remark_processed(submission_id)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

