#!/usr/bin/env python3
"""
Calculate conversion rate for the Holistic Wellness Hit List.

This script analyzes:
- Recently onboarded stores (4 specific stores)
- Eligible stores (only stores with status: Contacted, Manager Follow-up, or Rejected)
- Conversion rate = onboarded / eligible

Excludes stores that haven't been actively engaged:
- On Hold, Research (haven't done anything yet)
- Not Appropriate (bad targeting)
- Shortlisted (may not have been contacted yet)
"""

from __future__ import annotations

from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
WORKSHEET_NAME = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Recently onboarded stores (as specified by user)
RECENTLY_ONBOARDED = [
    "The Love of Ganesha",
    "Go Ask Alice",
    "Queen Hippie Gypsy",
    "Lumin Earth Apothecary",
]


def get_google_sheets_client() -> gspread.Client:
    """Get authenticated Google Sheets client."""
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    if not creds_path.exists():
        raise FileNotFoundError(
            f"google_credentials.json not found at {creds_path}. "
            "Please place your service account credentials in the repository root."
        )

    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def fetch_hit_list() -> pd.DataFrame:
    """Fetch the Hit List from Google Sheets."""
    client = get_google_sheets_client()
    worksheet = client.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

    print(f"✅ Connected to spreadsheet: {SPREADSHEET_ID}")
    print(f"   Worksheet: {WORKSHEET_NAME}")

    values = worksheet.get_all_values()
    if len(values) < 1:
        raise ValueError("Worksheet is empty.")

    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)

    print(f"📊 Retrieved {len(df)} rows with {len(df.columns)} columns.")
    return df


def normalize_store_name(name: str) -> str:
    """Normalize store name for comparison (case-insensitive, strip whitespace)."""
    if pd.isna(name):
        return ""
    return str(name).strip()


def is_recently_onboarded(store_name: str) -> bool:
    """Check if store is in the recently onboarded list."""
    normalized = normalize_store_name(store_name)
    return any(normalize_store_name(onboarded) == normalized for onboarded in RECENTLY_ONBOARDED)


def is_eligible_for_conversion(df_row: pd.Series) -> bool:
    """
    Determine if a store is eligible for conversion rate calculation.
    
    Only count stores where actual contact/effort has been made:
    - "Contacted" - Initial contact made
    - "Manager Follow-up" - Active follow-up in progress
    - "Rejected" - Contacted but declined
    
    Exclude:
    - "On Hold" - Haven't done anything yet
    - "Research" - Haven't done anything yet
    - "Not Appropriate" - Bad targeting (not a real opportunity)
    - "Shortlisted" - May or may not have been contacted yet
    - Other statuses - Not actively engaged
    """
    status = normalize_store_name(df_row.get("Status", ""))
    
    # Only these statuses indicate actual contact/effort was made
    eligible_statuses = ["Contacted", "Manager Follow-up", "Rejected"]
    
    return status in eligible_statuses


def calculate_conversion_rate(df: pd.DataFrame) -> dict:
    """Calculate conversion rate statistics."""
    # Filter out empty rows
    df = df[df.iloc[:, 0].notna()]  # First column should have store name
    
    # Find store name column (could be "Store Name", "Name", or first column)
    name_col = None
    for col in ["Store Name", "Name", df.columns[0]]:
        if col in df.columns:
            name_col = col
            break
    
    if name_col is None:
        raise ValueError("Could not find store name column")
    
    print(f"\n📋 Using '{name_col}' column for store names")
    
    # Identify recently onboarded stores
    onboarded_stores = []
    for idx, row in df.iterrows():
        store_name = normalize_store_name(row.get(name_col, ""))
        if is_recently_onboarded(store_name):
            onboarded_stores.append({
                "name": store_name,
                "status": normalize_store_name(row.get("Status", "")),
                "row": idx + 2,  # +2 because 0-indexed and header row
            })
    
    print(f"\n✅ Recently Onboarded Stores ({len(onboarded_stores)}):")
    for store in onboarded_stores:
        print(f"   - {store['name']} (Status: {store['status']}, Row: {store['row']})")
    
    # Find eligible stores (for conversion rate denominator)
    eligible_stores = []
    for idx, row in df.iterrows():
        store_name = normalize_store_name(row.get(name_col, ""))
        if not store_name:  # Skip empty rows
            continue
        
        # Skip if it's one of the recently onboarded stores
        if is_recently_onboarded(store_name):
            continue
        
        if is_eligible_for_conversion(row):
            status = normalize_store_name(row.get("Status", ""))
            eligible_stores.append({
                "name": store_name,
                "status": status,
                "row": idx + 2,
            })
    
    print(f"\n📊 Eligible Stores for Conversion Rate ({len(eligible_stores)}):")
    print(f"   (Only stores with status: Contacted, Manager Follow-up, or Rejected)")
    print(f"   (Excludes: On Hold, Research, Not Appropriate, Shortlisted, etc.)")
    
    # Group by status for summary
    status_counts = {}
    for store in eligible_stores:
        status = store["status"] or "(empty)"
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print(f"\n   Breakdown by Status:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"      - {status}: {count}")
    
    # Calculate conversion rate
    num_onboarded = len(onboarded_stores)
    num_eligible = len(eligible_stores)
    
    if num_eligible == 0:
        conversion_rate = 0.0
        print(f"\n⚠️  No eligible stores found. Cannot calculate conversion rate.")
    else:
        conversion_rate = (num_onboarded / num_eligible) * 100
        print(f"\n📈 Conversion Rate Calculation:")
        print(f"   Onboarded: {num_onboarded}")
        print(f"   Eligible:  {num_eligible}")
        print(f"   Rate:      {conversion_rate:.2f}%")
        print(f"   Formula:   {num_onboarded} / {num_eligible} × 100 = {conversion_rate:.2f}%")
    
    return {
        "onboarded_count": num_onboarded,
        "eligible_count": num_eligible,
        "conversion_rate": conversion_rate,
        "onboarded_stores": onboarded_stores,
        "eligible_stores": eligible_stores,
    }


def main() -> None:
    """Main function."""
    print("=" * 80)
    print("CONVERSION RATE ANALYSIS")
    print("=" * 80)
    print(f"\nRecently Onboarded Stores:")
    for store in RECENTLY_ONBOARDED:
        print(f"  - {store}")
    
    try:
        df = fetch_hit_list()
        results = calculate_conversion_rate(df)
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Recently Onboarded: {results['onboarded_count']}")
        print(f"Eligible Stores:    {results['eligible_count']}")
        print(f"Conversion Rate:     {results['conversion_rate']:.2f}%")
        print("=" * 80)
        
    except Exception as exc:
        print(f"\n❌ Error calculating conversion rate: {exc}")
        raise


if __name__ == "__main__":
    main()

