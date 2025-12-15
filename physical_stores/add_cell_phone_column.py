#!/usr/bin/env python3
"""
Add a "Cell Phone" column to the Hit List Google Sheet if it doesn't exist.

This script will:
1. Check if "Cell Phone" column exists
2. Add it after the "Phone" column if it doesn't exist
"""

from __future__ import annotations

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
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


def add_cell_phone_column() -> None:
    """Add Cell Phone column to Hit List if it doesn't exist."""
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        worksheet = spreadsheet.worksheet(HIT_LIST_SHEET)
    except gspread.WorksheetNotFound:
        raise ValueError(f'Worksheet "{HIT_LIST_SHEET}" not found.')

    # Get all values to find headers
    values = worksheet.get_all_values()
    if len(values) < 1:
        raise ValueError("Worksheet is empty.")
    
    headers = values[0]
    
    # Check if Cell Phone column already exists
    if "Cell Phone" in headers:
        print("✅ 'Cell Phone' column already exists in the Hit List.")
        print(f"   Column index: {headers.index('Cell Phone') + 1}")
        return
    
    # Find Phone column index
    if "Phone" not in headers:
        raise ValueError("'Phone' column not found. Cannot determine where to add 'Cell Phone' column.")
    
    phone_col_idx = headers.index("Phone")
    cell_phone_col_idx = phone_col_idx + 1  # Insert after Phone column
    
    print(f"📋 Current columns: {len(headers)}")
    print(f"📍 'Phone' column is at index {phone_col_idx + 1}")
    print(f"➕ Adding 'Cell Phone' column at index {cell_phone_col_idx + 1}...")
    
    # Insert a new column after Phone
    # In Google Sheets API, we need to insert a column
    # The column index is 1-based for the API
    worksheet.insert_cols([["Cell Phone"]], cell_phone_col_idx + 1)
    
    print(f"✅ Successfully added 'Cell Phone' column at index {cell_phone_col_idx + 1}")
    print(f"   The column is now available in your Google Sheet!")


if __name__ == "__main__":
    print("=" * 80)
    print("ADDING CELL PHONE COLUMN TO HIT LIST")
    print("=" * 80)
    print()
    
    try:
        add_cell_phone_column()
        print()
        print("=" * 80)
        print("✅ COMPLETE!")
        print("=" * 80)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


