#!/usr/bin/env python3
"""
Backup the Holistic Wellness Hit List from Google Sheets and check for missing lat/long.

This script:
1. Downloads the latest Hit List from Google Sheets
2. Creates a timestamped backup
3. Checks for entries with missing latitude/longitude
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

try:
    import gspread
    import pandas as pd
    from google.oauth2.service_account import Credentials
except ImportError:
    print("❌ Required packages not installed. Please run:")
    print("   pip install gspread pandas google-auth")
    exit(1)

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WORKSHEET = "Hit List"
HIT_LIST_OUTPUT = Path("data/hit_list.csv")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"google_credentials.json not found at {creds_path}. Please place your service account "
            "credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def backup_existing(path: Path) -> None:
    """Backup existing file with timestamp."""
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = path.with_suffix(f".csv.backup_{timestamp}")
        path.replace(backup_path)
        print(f"  ✅ Existing CSV backed up to: {backup_path}")


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
    if HIT_LIST_OUTPUT.exists():
        backup_existing(HIT_LIST_OUTPUT)

    # Ensure output directory exists
    HIT_LIST_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Save to CSV with UTF-8 BOM for Excel compatibility
    df.to_csv(HIT_LIST_OUTPUT, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8-sig")
    print(f"💾 Saved to {HIT_LIST_OUTPUT}")

    return df


def check_missing_coordinates(df: pd.DataFrame) -> None:
    """Check for entries with missing latitude or longitude."""
    print("\n" + "=" * 80)
    print("CHECKING FOR MISSING LATITUDE/LONGITUDE")
    print("=" * 80)
    
    # Normalize column names (handle BOM and whitespace)
    df.columns = df.columns.str.strip().str.replace('\ufeff', '')
    
    # Check if required columns exist
    if 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        print("❌ Latitude or Longitude columns not found in the data.")
        print(f"   Available columns: {', '.join(df.columns)}")
        return
    
    # Find entries with missing lat/long
    missing_lat = df['Latitude'].isna() | (df['Latitude'].astype(str).str.strip() == '')
    missing_lng = df['Longitude'].isna() | (df['Longitude'].astype(str).str.strip() == '')
    missing_coords = missing_lat | missing_lng
    
    total_missing = missing_coords.sum()
    print(f"\n📊 Found {total_missing} entries with missing latitude or longitude")
    
    if total_missing > 0:
        print("\n🔍 Entries with missing coordinates:")
        print("-" * 80)
        
        missing_df = df[missing_coords][['Shop Name', 'Address', 'City', 'State', 'Latitude', 'Longitude', 'Status']].copy()
        
        # Check specifically for Lumin Earth Apothecary
        lumin_entries = missing_df[missing_df['Shop Name'].str.contains('Lumin Earth', case=False, na=False)]
        
        if len(lumin_entries) > 0:
            print("\n⚠️  Lumin Earth Apothecary entries with missing coordinates:")
            for idx, row in lumin_entries.iterrows():
                print(f"\n   Shop: {row['Shop Name']}")
                print(f"   Address: {row['Address']}, {row['City']}, {row['State']}")
                print(f"   Status: {row['Status']}")
                print(f"   Latitude: {row['Latitude']} (missing)" if pd.isna(row['Latitude']) or str(row['Latitude']).strip() == '' else f"   Latitude: {row['Latitude']}")
                print(f"   Longitude: {row['Longitude']} (missing)" if pd.isna(row['Longitude']) or str(row['Longitude']).strip() == '' else f"   Longitude: {row['Longitude']}")
        
        # Show first 10 missing entries
        print("\n📋 First 10 entries with missing coordinates:")
        for idx, row in missing_df.head(10).iterrows():
            print(f"   - {row['Shop Name']} ({row['City']}, {row['State']}) - Status: {row['Status']}")
        
        if total_missing > 10:
            print(f"   ... and {total_missing - 10} more")
    else:
        print("✅ All entries have latitude and longitude coordinates!")


def main() -> None:
    """Main function."""
    print("=" * 80)
    print("BACKING UP HIT LIST AND CHECKING FOR MISSING COORDINATES")
    print("=" * 80)
    print()

    try:
        df = fetch_and_save_hit_list()
        
        if not df.empty:
            check_missing_coordinates(df)
            
            print("\n" + "=" * 80)
            print("✅ Backup complete!")
            print(f"   Location: {HIT_LIST_OUTPUT}")
            print("=" * 80)
        else:
            print("❌ No data retrieved from Google Sheets.")

    except FileNotFoundError as e:
        print(f"❌ {e}")
        exit(1)
    except Exception as exc:
        print(f"❌ Error: {exc}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()






