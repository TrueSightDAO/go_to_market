#!/usr/bin/env python3
"""Check what columns exist in the Hit List Google Sheet."""

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

SPREADSHEET_ID = "1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc"
HIT_LIST_SHEET = "Hit List"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main():
    creds_path = Path(__file__).parent.parent / "google_credentials.json"
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(creds)

    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(HIT_LIST_SHEET)

    headers = worksheet.row_values(1)
    print("Columns in Google Sheet:")
    for i, col in enumerate(headers, 1):
        print(f"{i}. {col}")

    print("\nChecking for specific columns:")
    if "Follow Up Date" in headers:
        print(f"  ✅ Follow Up Date: EXISTS at column {headers.index('Follow Up Date') + 1}")
    else:
        print("  ❌ Follow Up Date: NOT FOUND")

    if "Cell Phone" in headers:
        print(f"  ✅ Cell Phone: EXISTS at column {headers.index('Cell Phone') + 1}")
    else:
        print("  ❌ Cell Phone: NOT FOUND")

    # Find Spice of Life row
    all_values = worksheet.get_all_values()
    for i, row in enumerate(all_values[1:], start=2):
        shop_name_idx = headers.index("Shop Name") if "Shop Name" in headers else -1
        if shop_name_idx >= 0 and shop_name_idx < len(row) and "Spice of Life" in row[shop_name_idx]:
            print(f"\nSpice of Life (row {i}):")
            if "Follow Up Date" in headers:
                follow_up_idx = headers.index("Follow Up Date")
                value = row[follow_up_idx] if follow_up_idx < len(row) else "(empty)"
                print(f"  Follow Up Date: '{value}'")
            if "Cell Phone" in headers:
                cell_phone_idx = headers.index("Cell Phone")
                value = row[cell_phone_idx] if cell_phone_idx < len(row) else "(empty)"
                print(f"  Cell Phone: '{value}'")
            if "Phone" in headers:
                phone_idx = headers.index("Phone")
                value = row[phone_idx] if phone_idx < len(row) else "(empty)"
                print(f"  Phone: '{value}'")
            break


if __name__ == "__main__":
    main()


