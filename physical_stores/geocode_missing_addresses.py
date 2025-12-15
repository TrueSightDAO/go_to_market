#!/usr/bin/env python3
"""
Geocode missing addresses in the Holistic Wellness Hit List and update Google Sheets.

This script:
1. Connects to Google Sheets
2. Finds entries with missing latitude/longitude
3. Geocodes addresses using Nominatim (OpenStreetMap) - free, no API key needed
4. Updates the Google Sheet with the coordinates
5. Shows progress and results

Usage:
    python3 geocode_missing_addresses.py [--yes] [--dry-run]
    
    --yes      Skip confirmation prompt and proceed automatically
    --dry-run  Show what would be geocoded without updating the sheet
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import gspread
    import requests
    from google.oauth2.service_account import Credentials
except ImportError:
    print("❌ Required packages not installed. Please run:")
    print("   pip install gspread requests google-auth")
    exit(1)

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_WORKSHEET = "Hit List"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Rate limiting for Nominatim (1 request per second)
NOMINATIM_DELAY = 1.1


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


def geocode_address(address: str, city: str, state: str) -> tuple[float | None, float | None]:
    """
    Geocode an address using Nominatim (OpenStreetMap) - free and no API key needed.
    Returns (latitude, longitude) or (None, None) if geocoding fails.
    Tries multiple address formats for better matching.
    """
    # Clean address - remove suite/unit numbers for better matching
    clean_address = address.strip() if address else ""
    # Try to extract base address (before Suite/Unit/etc)
    if clean_address:
        for suffix in ["Suite", "Unit", "Space", "Ste", "Ste.", "Apt", "Apt."]:
            if suffix in clean_address:
                clean_address = clean_address.split(suffix)[0].strip()
                break
    
    # Try multiple address formats
    address_variants = []
    
    # Format 1: Full address with suite
    if address and city and state:
        address_variants.append(f"{address}, {city}, {state}, USA")
    
    # Format 2: Clean address without suite
    if clean_address and city and state:
        address_variants.append(f"{clean_address}, {city}, {state}, USA")
    
    # Format 3: Just street number and name + city + state
    if clean_address and city and state:
        # Extract just street number and name (first few words)
        street_parts = clean_address.split()[:3]  # Usually "123 Main St"
        if len(street_parts) >= 2:
            simple_street = " ".join(street_parts)
            address_variants.append(f"{simple_street}, {city}, {state}, USA")
    
    # Format 4: City + State only (as fallback)
    if city and state:
        address_variants.append(f"{city}, {state}, USA")
    
    # Try each variant
    for full_address in address_variants:
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": full_address,
                "format": "json",
                "limit": 1,
                "addressdetails": 1
            }
            headers = {
                "User-Agent": "MarketResearchBot/1.0 (https://github.com/TrueSightDAO)"  # Required by Nominatim
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                display_name = data[0].get("display_name", full_address)
                return lat, lon
        except Exception as e:
            continue  # Try next variant
    
    return None, None


def find_column_index(headers: list, column_name: str) -> int | None:
    """Find the index of a column by name (case-insensitive, handles BOM)."""
    normalized_name = column_name.strip().replace('\ufeff', '').lower()
    for idx, header in enumerate(headers):
        if header.strip().replace('\ufeff', '').lower() == normalized_name:
            return idx
    return None


def main() -> None:
    """Main function to geocode missing addresses."""
    parser = argparse.ArgumentParser(description='Geocode missing addresses in Hit List')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    args = parser.parse_args()
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made to the sheet")
        print()
    
    print("=" * 80)
    print("GEOCODING MISSING ADDRESSES IN HIT LIST")
    print("=" * 80)
    print()

    try:
        # Connect to Google Sheets
        print("📡 Connecting to Google Sheets...")
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(HIT_LIST_WORKSHEET)
        print(f"✅ Connected to worksheet: {HIT_LIST_WORKSHEET}")
        print()

        # Get all data
        print("📖 Reading data from Google Sheets...")
        all_values = worksheet.get_all_values()
        
        if len(all_values) < 2:
            print("❌ No data found in worksheet (need at least header + 1 row)")
            return
        
        headers = all_values[0]
        rows = all_values[1:]
        
        print(f"📊 Found {len(rows)} rows")
        print()

        # Find column indices
        shop_name_idx = find_column_index(headers, "Shop Name")
        address_idx = find_column_index(headers, "Address")
        city_idx = find_column_index(headers, "City")
        state_idx = find_column_index(headers, "State")
        lat_idx = find_column_index(headers, "Latitude")
        lng_idx = find_column_index(headers, "Longitude")
        status_idx = find_column_index(headers, "Status")

        if None in [shop_name_idx, address_idx, city_idx, state_idx, lat_idx, lng_idx]:
            print("❌ Required columns not found:")
            missing = []
            if shop_name_idx is None: missing.append("Shop Name")
            if address_idx is None: missing.append("Address")
            if city_idx is None: missing.append("City")
            if state_idx is None: missing.append("State")
            if lat_idx is None: missing.append("Latitude")
            if lng_idx is None: missing.append("Longitude")
            print(f"   Missing: {', '.join(missing)}")
            print(f"   Available columns: {', '.join(headers)}")
            return

        # Find rows with missing coordinates
        missing_coords = []
        for row_idx, row in enumerate(rows, start=2):  # Start at row 2 (row 1 is header)
            # Pad row if needed
            while len(row) < len(headers):
                row.append("")
            
            lat = row[lat_idx].strip() if lat_idx < len(row) else ""
            lng = row[lng_idx].strip() if lng_idx < len(row) else ""
            
            if not lat or not lng:
                shop_name = row[shop_name_idx].strip() if shop_name_idx < len(row) else ""
                address = row[address_idx].strip() if address_idx < len(row) else ""
                city = row[city_idx].strip() if city_idx < len(row) else ""
                state = row[state_idx].strip() if state_idx < len(row) else ""
                status = row[status_idx].strip() if status_idx and status_idx < len(row) else ""
                
                if address or city:  # Only geocode if we have at least an address or city
                    missing_coords.append({
                        'row': row_idx,
                        'shop_name': shop_name,
                        'address': address,
                        'city': city,
                        'state': state,
                        'status': status
                    })

        print(f"🔍 Found {len(missing_coords)} entries with missing coordinates")
        print()

        if not missing_coords:
            print("✅ All entries already have coordinates!")
            return

        # Show entries to be geocoded
        print("📋 Entries to geocode:")
        for entry in missing_coords:
            print(f"   - {entry['shop_name']} ({entry['city']}, {entry['state']}) - Status: {entry['status']}")
        print()

        # Ask for confirmation (unless --yes flag is provided)
        if not args.yes:
            try:
                response = input("Proceed with geocoding? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    print("❌ Geocoding cancelled.")
                    return
            except (EOFError, KeyboardInterrupt):
                print("\n❌ Geocoding cancelled (no input available).")
                print("   Use --yes flag to skip confirmation.")
                return

        print()
        print("🌍 Starting geocoding...")
        print("   (Using Nominatim - free, but rate-limited to 1 request/second)")
        print()

        # Geocode and update
        updated = 0
        failed = 0
        
        for i, entry in enumerate(missing_coords, 1):
            print(f"[{i}/{len(missing_coords)}] Geocoding: {entry['shop_name']}")
            print(f"   Address: {entry['address']}, {entry['city']}, {entry['state']}")
            
            lat, lng = geocode_address(entry['address'], entry['city'], entry['state'])
            
            if lat and lng:
                if args.dry_run:
                    print(f"   ✅ Would update: ({lat}, {lng})")
                    updated += 1
                else:
                    # Update the sheet
                    worksheet.update_cell(entry['row'], lat_idx + 1, lat)  # +1 because gspread is 1-indexed
                    worksheet.update_cell(entry['row'], lng_idx + 1, lng)
                    print(f"   ✅ Updated: ({lat}, {lng})")
                    updated += 1
            else:
                print(f"   ❌ Failed to geocode")
                failed += 1
            
            # Rate limiting - wait between requests
            if i < len(missing_coords):
                time.sleep(NOMINATIM_DELAY)
            print()

        # Summary
        print("=" * 80)
        if args.dry_run:
            print("✅ Dry run complete!")
            print(f"   Would update: {updated} entries")
        else:
            print("✅ Geocoding complete!")
            print(f"   Updated: {updated} entries")
        if failed > 0:
            print(f"   Failed: {failed} entries")
        print("=" * 80)

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

