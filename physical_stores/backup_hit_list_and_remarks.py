#!/usr/bin/env python3
"""
Backup the latest Holistic Wellness Hit List and DApp Remarks from Google Sheets to local CSV files.

This script downloads both:
1. Hit List - Main store database with status, contact info, notes
2. DApp Remarks - Status updates and remarks from stores_nearby.html DApp

Use this to create local backups of your Google Sheet data.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WORKSHEET = "Hit List"
DAPP_REMARKS_WORKSHEET = "DApp Remarks"
HIT_LIST_OUTPUT = Path("data/hit_list.csv")
DAPP_REMARKS_OUTPUT = Path("data/dapp_remarks.csv")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def ensure_output_directory(path: Path) -> None:
    """Ensure the output directory exists."""
    path.parent.mkdir(parents=True, exist_ok=True)


def backup_existing(path: Path) -> None:
    """Backup existing file with timestamp."""
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".csv.backup_{timestamp}")
        path.replace(backup_path)
        print(f"  ✅ Existing CSV backed up to: {backup_path}")


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
    # Look for credentials in parent directory (repository root)
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"google_credentials.json not found at {creds_path}. Please place your service account "
            "credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def fetch_worksheet(worksheet_name: str) -> pd.DataFrame:
    """Fetch data from a specific worksheet."""
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        print(f"  ⚠️  Worksheet '{worksheet_name}' not found. Skipping...")
        return pd.DataFrame()

    print(f"✅ Connected to worksheet: {worksheet_name}")

    values = worksheet.get_all_values()
    if len(values) < 1:
        print(f"  ⚠️  Worksheet '{worksheet_name}' is empty.")
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    print(f"📊 Retrieved {len(df)} rows with {len(df.columns)} columns from '{worksheet_name}'")

    return df


def save_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Save DataFrame to CSV with UTF-8 BOM encoding for Excel compatibility."""
    ensure_output_directory(path)

    if df.empty:
        print(f"  ⚠️  No data to save to {path}")
        return

    # Use UTF-8 with BOM to retain compatibility with Excel
    df.to_csv(path, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")
    print(f"💾 Saved to {path}")


def main() -> None:
    """Main function to backup both Hit List and DApp Remarks."""
    print("=" * 80)
    print("BACKING UP HIT LIST AND DAPP REMARKS FROM GOOGLE SHEETS")
    print("=" * 80)
    print()

    try:
        # Backup Hit List
        print("📋 Downloading Hit List...")
        hit_list_df = fetch_worksheet(HIT_LIST_WORKSHEET)
        if not hit_list_df.empty:
            backup_existing(HIT_LIST_OUTPUT)
            save_to_csv(hit_list_df, HIT_LIST_OUTPUT)
            
            print("\n  Hit List Summary:")
            if "Status" in hit_list_df.columns:
                status_counts = hit_list_df["Status"].value_counts().to_dict()
                for status, count in status_counts.items():
                    print(f"    - {status}: {count}")
            print()

        # Backup DApp Remarks
        print("💬 Downloading DApp Remarks...")
        remarks_df = fetch_worksheet(DAPP_REMARKS_WORKSHEET)
        if not remarks_df.empty:
            backup_existing(DAPP_REMARKS_OUTPUT)
            save_to_csv(remarks_df, DAPP_REMARKS_OUTPUT)
            
            print("\n  DApp Remarks Summary:")
            if "Processed" in remarks_df.columns:
                processed_counts = remarks_df["Processed"].value_counts().to_dict()
                for status, count in processed_counts.items():
                    print(f"    - {status}: {count}")
            print(f"    - Total remarks: {len(remarks_df)}")
            print()

        print("=" * 80)
        print("✅ Backup complete!")
        print(f"   - Hit List: {HIT_LIST_OUTPUT}")
        print(f"   - DApp Remarks: {DAPP_REMARKS_OUTPUT}")
        print("=" * 80)

    except Exception as exc:  # pylint: disable=broad-except
        print(f"❌ Error backing up data: {exc}")
        raise


if __name__ == "__main__":
    main()

