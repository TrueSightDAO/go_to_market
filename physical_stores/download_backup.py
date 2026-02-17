#!/usr/bin/env python3
"""
Download the latest backup of the Holistic Wellness Hit List from Google Sheets.

This script downloads the Hit List data and creates a timestamped backup
following the same pattern as other backup scripts in this directory.

Usage:
    python download_backup.py
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
HIT_LIST_OUTPUT = Path("data/hit_list.csv")
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


def fetch_and_save_hit_list() -> pd.DataFrame:
    """Fetch data from Hit List worksheet and save to CSV."""
    print("📋 Downloading Hit List from Google Sheets...")
    client = get_google_sheets_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    try:
        worksheet = spreadsheet.worksheet(HIT_LIST_WORKSHEET)
    except gspread.WorksheetNotFound:
        print(f"  ❌ Worksheet '{HIT_LIST_WORKSHEET}' not found.")
        return pd.DataFrame()

    print(f"✅ Connected to worksheet: {HIT_LIST_WORKSHEET}")

    values = worksheet.get_all_values()
    if len(values) < 1:
        print(f"  ⚠️  Worksheet '{HIT_LIST_WORKSHEET}' is empty.")
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    print(f"📊 Retrieved {len(df)} rows with {len(df.columns)} columns")

    # Backup existing file
    backup_existing(HIT_LIST_OUTPUT)

    # Ensure output directory exists
    ensure_output_directory(HIT_LIST_OUTPUT)

    # Save to CSV with UTF-8 BOM for Excel compatibility
    df.to_csv(HIT_LIST_OUTPUT, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")
    print(f"💾 Saved to {HIT_LIST_OUTPUT}")

    return df


def main() -> None:
    """Main function to download and backup Hit List."""
    print("=" * 80)
    print("DOWNLOADING LATEST HIT LIST BACKUP FROM GOOGLE SHEETS")
    print("=" * 80)
    print()

    try:
        df = fetch_and_save_hit_list()
        
        if not df.empty:
            print("\n  Hit List Summary:")
            if "Status" in df.columns:
                status_counts = df["Status"].value_counts().to_dict()
                for status, count in status_counts.items():
                    print(f"    - {status}: {count}")
            print(f"    - Total stores: {len(df)}")
            print()

        print("=" * 80)
        print("✅ Backup download complete!")
        print(f"   Location: {HIT_LIST_OUTPUT}")
        print("=" * 80)

    except FileNotFoundError as e:
        print(f"❌ {e}")
        exit(1)
    except Exception as exc:
        print(f"❌ Error downloading backup: {exc}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()





